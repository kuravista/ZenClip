from utils.logger import log
import utils.encoding_fix
import os
import sys
import json
import time
import threading
import uuid
import shutil
from enum import Enum
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from services.core.composite_metadata_persistence import CompositeMetadataPersistence
from services.core.local_priority_job_queue import LocalPriorityJobQueue
from services.core.thread_pipeline_runner import ThreadPipelineRunner

if TYPE_CHECKING:
    from services.core.ports.context import JobRequestContext

class JobStatus(Enum):
    QUEUED = "queued"
    PREPARING = "preparing" # Downloading or verifying upload
    TRANSCRIBING = "transcribing"
    ANALYZING = "analyzing"
    WAITING_REVIEW = "waiting_review"
    CUTTING = "cutting"
    COMPLETE = "complete"
    ERROR = "error"
    CANCELLED = "cancelled"


def should_skip_pipeline_for_metadata(meta) -> bool:
    """True when worker must not invoke JobRunner (e.g. already cancelled while queued)."""
    if not meta:
        return False
    return meta.get("status") == JobStatus.CANCELLED.value


class JobManager:
    _instance = None
    _lock = threading.RLock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(JobManager, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
            
        # Use a writable, persistent path in production (sidecar/frozen mode)
        # to avoid read-only issues when installed to C:\Program Files
        _jobs_dir_override = os.environ.get('CLIP_JOBS_DIR')
        _app_data_override = os.environ.get('CLIP_APP_DATA_DIR')
        _default_app_data = os.environ.get('CLIP_DEFAULT_APP_DATA_DIR')
        _sidecar_dir = os.environ.get('CLIP_SIDECAR_DIR')
        if _jobs_dir_override:
            self.jobs_dir = _jobs_dir_override
        elif _app_data_override:
            from pathlib import Path
            self.jobs_dir = str(Path(_app_data_override) / 'jobs_data')
        elif _default_app_data:
            from pathlib import Path
            self.jobs_dir = str(Path(_default_app_data) / 'jobs_data')
        elif getattr(sys, 'frozen', False) or _sidecar_dir:
            from pathlib import Path
            _app_data = Path.home() / 'Documents' / 'SnipieAI'
            self.jobs_dir = str(_app_data / 'jobs_data')
        else:
            # Dev mode: use a relative path in the project root
            self.jobs_dir = "jobs_data"
        os.makedirs(self.jobs_dir, exist_ok=True)

        self._persistence = CompositeMetadataPersistence(self.jobs_dir)
        self._queue = LocalPriorityJobQueue()
        self.active_job_id = None
        self.worker_thread = None
        self.running = False
        
        # Load jobs from disk on startup (simple metadata read)
        # We don't auto-queue them yet, but we could if we want strictly robust resume
        # For now, we will rely on client to ask or manual resume, or just listing them.
        
        self.start_worker()
        self._recover_jobs()
        self._initialized = True

    def _recover_jobs(self):
        """Scan jobs folder on startup and mark stuck jobs as interrupted"""
        log.step("Checking for interrupted jobs", module="JobManager")
        try:
            if not os.path.exists(self.jobs_dir): return
            
            # DISABLED: This was too aggressive and marked resumable jobs as ERROR
            # Jobs can be legitimately resumed via /process_with_transcript
            # Only enable this if we implement proper job locking or timestamps
            
            # for job_id in os.listdir(self.jobs_dir):
            #     job_path = os.path.join(self.jobs_dir, job_id)
            #     if not os.path.isdir(job_path): continue
            #     
            #     meta = self._load_job_file(job_id, "metadata.json")
            #     if not meta: continue
            #     
            #     # If job was in a 'running' state when app started, it was interrupted
            #     run_states = [
            #         JobStatus.PREPARING.value,
            #         JobStatus.TRANSCRIBING.value,
            #         JobStatus.ANALYZING.value,
            #         JobStatus.CUTTING.value
            #     ]
            #     
            #     if meta.get("status") in run_states:
            #         print(f"[WARN] Job {job_id} was interrupted during {meta.get('status')}. Marking as error.")
            #         self.update_job_status(job_id, JobStatus.ERROR, error_msg="Job interrupted by system restart")

        except Exception as e:
            log.error(f"Job recovery failed: {e}", module="JobManager")

    def stop_all(self):
        """Gracefully stop the worker and cancel active job"""
        log.info("Stopping job manager", module="JobManager")
        self.running = False
        
        # Signal worker to stop
        self._queue.put_stop()
        
        # If there's an active job, try to cancel it
        with self._lock:
            if self.active_job_id:
                log.warn(f"Cancelling active job on shutdown: {self.active_job_id}", module="JobManager")
                self.update_job_status(self.active_job_id, JobStatus.CANCELLED, error_msg="System shutdown")
                # In real scenario, we might need to kill the subprocess if JobRunner uses Popen
                # Since JobRunner runs in this thread (mostly), we can't force kill it easily without process kill
                # But flagging it as cancelled might help if it checks status periodically
        
        if self.worker_thread and self.worker_thread.is_alive():
             self.worker_thread.join(timeout=2.0)


    def start_worker(self):
        if self.running: return
        self.running = True
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
        log.success("Job Manager worker started", module="JobManager")

    def _worker_loop(self):
        while self.running:
            try:
                queue_item = self._queue.blocking_dequeue()

                if queue_item is None:
                    break

                if isinstance(queue_item, tuple):
                    _, _, job_id = queue_item
                else:
                    job_id = queue_item

                meta = self._persistence.load_metadata(job_id)
                if should_skip_pipeline_for_metadata(meta):
                    self._queue.task_done()
                    continue

                with self._lock:
                    self.active_job_id = job_id

                log.section(f"Job: {job_id}")
                log.step(f"Starting job: {job_id}", module="JobManager")
                try:
                    if os.environ.get("CLIP_PIPELINE_RUNNER", "").lower() == "multiprocess_stub":
                        from services.core.process_pipeline_runner_stub import (
                            MultiprocessPipelineRunnerStub,
                        )

                        runner = MultiprocessPipelineRunnerStub(self)
                    else:
                        runner = ThreadPipelineRunner(self)
                    runner.run(job_id, self.jobs_dir)
                except Exception as e:
                    log.error(f"Critical worker error on job {job_id}: {e}", module="JobManager")

                    # Ensure job is marked error if runner failed completely
                    self.update_job_status(job_id, JobStatus.ERROR, error_msg=str(e))
                finally:
                    with self._lock:
                        self.active_job_id = None
                    self._queue.task_done()
                    
            except Exception as e:
                log.error(f"Worker loop error: {e}", module="JobManager")
                time.sleep(1)

    def submit_job(self, job_data, priority=5, ctx: Optional["JobRequestContext"] = None):
        """
        Creates a new job, saves initial metadata, and adds to queue.
        job_data: dict containing 'type' (upload/youtube), params, etc.
        priority: int (0=highest priority, 10=lowest priority, default=5)
        ctx: optional tenancy / user context (ignored by default stores).
        """
        job_id = str(uuid.uuid4())
        job_dir = os.path.join(self.jobs_dir, job_id)

        os.makedirs(job_dir, exist_ok=True)

        initial_state = {
            "id": job_id,
            "created_at": time.time(),
            "status": JobStatus.QUEUED.value,
            "progress": "Waiting in queue...",
            "priority": priority,
            "data": job_data,
            "history": [],
        }
        if ctx is not None:
            initial_state["context"] = ctx.to_metadata_dict()

        self._persistence.save_initial_job(job_id, initial_state)

        self._queue.enqueue(job_id, priority=float(priority))
        log.info(f"Job queued: {job_id} (priority={priority})", module="JobManager")

        return job_id

    def get_job(self, job_id):
        return self._persistence.load_metadata(job_id)

    def update_job_status(self, job_id, status: JobStatus, progress_msg=None, error_msg=None, progress_percent=None):
        """
        Thread-safe update of job status file
        """
        # We need to lock efficiently. File writes are theoretically atomic-ish but let's be safe.
        # Ideally JobRunner handles its own state updates, but Manager might need to force update (cancel, error)
        
        # For simplicity, we read-modify-write.
        # In high concurrency this is bad, but we have 1 worker.

        meta = self._persistence.load_metadata(job_id)
        if not meta:
            return
        
        meta["status"] = status.value
        if progress_msg:
            meta["progress_msg"] = progress_msg # Use progress_msg for text 
            # We keep 'progress' as legacy/fallback if needed, or switch convention.
            # Let's keep 'progress' for text to avoid breaking other things, and add 'percentage'
            meta["progress"] = progress_msg 
            
        if progress_percent is not None:
            meta["percentage"] = progress_percent

        if error_msg:
            meta["error"] = error_msg
        
        meta["last_updated"] = time.time()
        
        if status == JobStatus.COMPLETE or status == JobStatus.ERROR:
             meta["completed_at"] = time.time()
             if status == JobStatus.COMPLETE:
                 meta["percentage"] = 100
             
             # CLARIFICATION: Aggressive cleanup of uploaded source file to save space
             # DISABLED: User wants to keep uploaded files in library.
             # job_data = meta.get('data', {})
             # if job_data.get('video_file') is True:
             #     filepath = job_data.get('filepath')
             #     if filepath and os.path.exists(filepath):
             #         try:
             #             os.remove(filepath)
             #             print(f"🧹 Cleaned up source file: {filepath}")
             #         except Exception as e:
             #             print(f"⚠️ Failed to cleanup source file {filepath}: {e}")
        
        self._persistence.save_metadata(job_id, meta)

    def _save_job_file(self, job_id, filename, data):
        if filename == "metadata.json":
            self._persistence.save_metadata(job_id, data)
            return
        path = os.path.join(self.jobs_dir, job_id, filename)
        temp_path = path + ".tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(temp_path, path)
        except Exception as e:
            log.warn(f"Failed to save job file {filename}: {e}", module="JobManager")

    def _load_job_file(self, job_id, filename):
        if filename == "metadata.json":
            return self._persistence.load_metadata(job_id)
        path = os.path.join(self.jobs_dir, job_id, filename)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def update_job_data(self, job_id, updates):
        """
        Updates the 'data' field in metadata.json.
        Used for updating parameters (like edited transcript) before resuming.
        """
        meta = self._persistence.load_metadata(job_id)
        if not meta:
            return False

        if "data" not in meta:
            meta["data"] = {}
        meta["data"].update(updates)

        self._persistence.save_metadata(job_id, meta)
        return True

    def resume_job(self, job_id):
        """Force re-queue a job if not already running"""
        if self.active_job_id == job_id:
            return False # Already running
            
        # Check if already in queue? (Harder with Queue class)
        # For now, assume if user clicks resume, we re-queue.
        # Reset status to QUEUED if it was error or stalled
        meta = self.get_job(job_id)
        if meta and meta['status'] not in ['queued', 'processing', 'running']: # Wait, checking internal statuses
             # Basically if it's not currently active.
             # We change status to QUEUED and put in queue
             self.update_job_status(job_id, JobStatus.QUEUED, progress_msg="Resuming job...")

             priority = meta.get("priority", 5)
             self._queue.enqueue(job_id, priority=float(priority))
             return True
        return False

    def cancel_job(self, job_id):
        """
        Cancels a job.
        If it's in the queue, just mark it as cancelled (worker will ignore it or handle it).
        If it's active, we mark it as cancelled and terminate the process.
        """
        log.info(f"Cancellation requested: {job_id}", module="JobManager")
        
        # 1. Update status on disk immediately
        self.update_job_status(job_id, JobStatus.CANCELLED, progress_msg="Job cancelled by user.")
        
        # 2. Check if it's the active job and terminate the process
        with self._lock:
            if self.active_job_id == job_id:
                log.step(f"Marking active job for cancellation: {job_id}", module="JobManager")
                # We cannot force kill the thread easily.
                # We rely on JobRunner deep checks (check_cancelled) to stop execution.
                # We unassign active_job_id so the manager knows it's 'done' with this job's slot
                # (though the thread might take a moment to spin down)
                self.active_job_id = None
                log.success(f"Job marked for cancellation: {job_id}", module="JobManager")
                return True
                
        # 3. Check queue (optional optimization to remove it)
        # Queue doesn't support random removal. 
        # But when worker picks it up, it should check status.
        return True

# Global instance
job_manager = JobManager()
