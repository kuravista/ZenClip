from utils.logger import log
import utils.encoding_fix
import os
import time
import json

from typing import Dict, Optional

from services.core.job_manager import JobStatus
from services.core.job_status_adapter import ManagerJobOrchestrationAdapter
from services.core.ports.protocols import JobPersistencePort, JobRunnerHostPort
from services.core.resource_monitor import get_resource_monitor, set_process_priority
from services.media.audio_transcriber import clean_repetitive_content, clean_phrase_level_repetition


# We need to import the actual logic functions.
# Since I haven't refactored tasks.py yet, I will import them as is and adapt.
# But `tasks.py` currently relies on global `jobs` dict.
# I MUST refactor `tasks.py` BEFORE `job_runner.py` works perfectly.
# strategies:
# 1. Create job_runner.py with placeholders calling stateless versions of tasks.
# 2. Refactor tasks.py to be stateless.

# Let's create job_runner first with the INTENTION of calling stateless functions.

class JobRunner:
    def __init__(
        self,
        job_id,
        jobs_dir,
        job_host: Optional[JobRunnerHostPort] = None,
        metadata_store: Optional[JobPersistencePort] = None,
    ):
        self.job_id = job_id
        self.jobs_dir = jobs_dir
        self.job_dir = os.path.join(jobs_dir, job_id)

        if job_host is None:
            from services.core.job_manager import job_manager as _jm

            self._job_host: JobRunnerHostPort = ManagerJobOrchestrationAdapter(_jm)
        else:
            self._job_host = job_host

        self._meta_store = metadata_store

        self.resource_monitor = get_resource_monitor()

        set_process_priority()
        
    def _load_metadata(self) -> Dict:
        if self._meta_store is not None:
            data = self._meta_store.load_metadata(self.job_id)
            if data is not None:
                return data
        with open(os.path.join(self.job_dir, "metadata.json"), "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_artifact(self, filename, data):
        with open(os.path.join(self.job_dir, filename), 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _load_artifact(self, filename):
        path = os.path.join(self.job_dir, filename)
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None

    def _is_cancelled(self):
        """Checks if the job has been marked as cancelled."""
        meta = self._load_metadata()
        if meta and meta.get('status') == JobStatus.CANCELLED.value:
            log.warn(f"Cancellation detected, stopping runner", module="JobRunner", job=self.job_id)
            return True
        return False

    def _parse_time_str(self, time_str):
        try:
            if not time_str: return 0.0
            parts = str(time_str).split(':')
            if len(parts) == 2:
                return float(parts[0]) * 60 + float(parts[1])
            elif len(parts) == 3:
                return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
            return float(time_str)
        except:
            return 0.0

    def run(self):
        """
        Main execution pipeline.
        Checks for existing artifacts to determine if steps can be skipped (Resume).
        """
        import time as _time
        _pipeline_start = _time.time()
        if self._is_cancelled(): return

        meta = self._load_metadata()
        data = meta['data']
        
        # 1. PREPARING (Download or Upload Verification)
        self._job_host.update_job_status(self.job_id, JobStatus.PREPARING, "Preparing video...", progress_percent=10)
        
        video_path = None
        video_info_path = os.path.join(self.job_dir, "video_info.json")
        
        if os.path.exists(video_info_path):
            video_info = self._load_artifact("video_info.json")
            video_path = video_info['path']
            log.info(f"Resuming: video already downloaded", module="JobRunner")
        else:
            # Execute Download/Prep
            try:
                if 'video_file' in data: # Upload case (logic might vary if we just passed path)
                     # In existing app.py, upload is saved immediately.
                     # data should contain 'filepath'
                     video_path = data.get('filepath') 
                     # Verify existence
                     if not os.path.exists(video_path):
                         raise FileNotFoundError(f"Uploaded file missing: {video_path}")
                
                elif 'url' in data:
                    # YouTube / URL download via yt-dlp
                    from services.media.yt_downloader import download_for_job, YtDownloaderError

                    download_url = data['url']
                    quality = data.get('yt_quality', '720p')
                    download_dir = data.get('download_folder', 'downloads')

                    print(f"  [JobRunner] URL download: {download_url} quality={quality}")

                    try:
                        video_path = download_for_job(
                            url=download_url,
                            quality=quality,
                            output_dir=download_dir,
                            job_id=self.job_id,
                            check_cancelled=self._is_cancelled,
                        )
                        print(f"  [JobRunner] Downloaded to: {video_path}")
                    except YtDownloaderError as e:
                        raise ValueError(f"YouTube download failed: {e}")

                    data['video_file'] = True
                    data['filepath'] = video_path
                    data['source_url'] = download_url
                
                self._save_artifact("video_info.json", {"path": video_path})
            
            except Exception as e:
                # Retry handled by loop? Or just fail?
                # For now fail.
                raise e

        if self._is_cancelled(): return

        # 2. TRANSCRIBING
        self._job_host.update_job_status(self.job_id, JobStatus.TRANSCRIBING, "Extracting transcript (AI)...", progress_percent=30)
        
        transcript_path = os.path.join(self.job_dir, "transcript.json")
        phrase_timings = None
        language = 'en'
        
        if os.path.exists(transcript_path):
             phrase_timings = self._load_artifact("transcript.json")
             # CRITICAL FIX: Clean Repetition on resume/manual steps
             
             phrase_timings = clean_repetitive_content(phrase_timings)
             phrase_timings = clean_phrase_level_repetition(phrase_timings)
             
             language = meta.get('data', {}).get('language', 'en')
             log.info(f"Resuming: transcript found ({len(phrase_timings)} phrases, lang={language})", module="JobRunner")
        else:
            from services.core.tasks_stateless import transcribe_step
            # params: video_path, mode
            mode = data.get('transcription_mode', 'fast')
            # CHECK_CANCELLED: Pass callback to allow deep cancellation during transcription
            phrase_timings, language = transcribe_step(video_path, mode, check_cancelled=self._is_cancelled)
            self._save_artifact("transcript.json", phrase_timings)
            
            # Save detected language to metadata for future use
            self._job_host.update_job_data(self.job_id, {"language": language})
            # Also update local 'data' dict so analyze step uses it if we re-read? 
            # Actually we pass 'language' variable directly.

        if self._is_cancelled(): return

        # 3. ANALYZING
        self._job_host.update_job_status(self.job_id, JobStatus.ANALYZING, "Analyzing content for viral clips...", progress_percent=60)
        
        analysis_path = os.path.join(self.job_dir, "analysis.json")
        clips_data = None
        
        if os.path.exists(analysis_path):
            clips_data = self._load_artifact("analysis.json")
            log.info(f"Resuming: analysis found ({len(clips_data)} clips)", module="JobRunner")
        elif data.get('manual_cut', False):
            # MANUAL CUT MODE
            log.info("Manual cut mode", module="JobRunner")
            # Disable auto-extension for manual cuts
            data['min_duration'] = 0
            import json
            
            manual_segments = []
            try:
                ms_raw = data.get('manual_segments', '[]')
                if ms_raw and ms_raw != 'None':
                     manual_segments = json.loads(ms_raw)
            except Exception as e:
                log.warn(f"Failed to parse manual_segments: {e}", module="JobRunner")

            clips_data = []

            # If we have segments, use them
            if manual_segments and isinstance(manual_segments, list) and len(manual_segments) > 0:
                # Enforce Max 5 Limit for Manual
                if len(manual_segments) > 5:
                    log.warn(f"Too many segments, limiting to 5", module="JobRunner")
                    manual_segments = manual_segments[:5]
                
                log.info(f"Processing {len(manual_segments)} manual segments", module="JobRunner")
                for i, seg in enumerate(manual_segments):
                    # Frontend usually sends {id, start, end}
                    start_str = seg.get('start', '00:00')
                    end_str = seg.get('end', '00:30')
                    
                    start_time = self._parse_time_str(start_str)
                    end_time = self._parse_time_str(end_str)
                    
                    # Validation and warnings
                    if start_time == 0.0 and start_str not in ['0', '00:00', '0:00']:
                        log.warn(f"Segment {i+1}: bad start time '{start_str}', defaulting to 00:00", module="JobRunner")
                    
                    if end_time == 0.0 and end_str not in ['0', '00:00', '0:00']:
                        log.warn(f"Segment {i+1}: bad end time '{end_str}', defaulting to 00:00", module="JobRunner")
                    
                    # Check for invalid range
                    if end_time <= start_time:
                        log.warn(f"Segment {i+1}: invalid range {start_str}→{end_str}", module="JobRunner")
                        
                        end_time = start_time + 30
                    
                    # Check for very short clips
                    duration = end_time - start_time
                    if duration < 1.0:
                        print(f"[INFO] Segment {i+1}: Short clip detected ({duration:.2f}s)")
                    
                    clips_data.append({
                        "start_time": start_time,
                        "end_time": end_time,
                        "topic": "Manual Cut",
                        "viral_score": 100,
                        "reason": f"Manual Selection {i+1}",
                        "hook_heading": "Manual Clip",
                        "hook_subheading": "",
                        "viral_caption": "Manual Clip"
                    })
            else:
                # Legacy Fallback (single start/end)
                start_time = self._parse_time_str(data.get('manual_start', '0'))
                end_time = self._parse_time_str(data.get('manual_end', '0'))

                if end_time <= start_time:
                     print(f"[WARN] Invalid manual times {start_time}-{end_time}, forcing 30s")
                     end_time = start_time + 30
                     
                clips_data = [{
                    "start_time": start_time,
                    "end_time": end_time,
                    "topic": "Manual Cut",
                    "viral_score": 100,
                    "reason": "User manual selection",
                    "hook_heading": "Manual Clip",
                    "hook_subheading": "",
                    "viral_caption": "Manual Clip"
                }]
            
            self._save_artifact("analysis.json", clips_data)
        else:
            from services.core.tasks_stateless import analyze_step
            # params: transcript, num_clips, min_duration, ...
            # I need flexible params from data
            # Determine hook style for prompt optimization
            hook_style = 'preset-1'
            if data.get('add_viral_hook') and data.get('hook_styles'):
                hook_style = data['hook_styles'].get('hook_style', 'preset-1')

            # CHECK_CANCELLED: Pass callback to allow deep cancellation during analysis
            clips_data = analyze_step(
                phrase_timings, 
                min(data.get('num_clips', 3), 5),  # Enforce Max 5 Limit for Auto 
                data.get('min_duration', 30),
                data.get('video_type', 'general'),
                data.get('custom_prompt'),
                data.get('api_key'),
                data.get('api_provider'),
                hook_style=hook_style,
                language=language,
                check_cancelled=self._is_cancelled
            )
            self._save_artifact("analysis.json", clips_data)

        if self._is_cancelled(): return

        # 4. WAITING_REVIEW (Optional)
        # If the flow demands review, we stop here.
        # Check data['require_review'] or similar.
        # Existing logic: extract_transcript endpoint stops here. process endpoint continues.
        # Let's support an explicit flag.
        if data.get('stop_for_review', False):
            self._job_host.update_job_status(self.job_id, JobStatus.WAITING_REVIEW, "Waiting for user review...", progress_percent=70)
            return # Exit runner. Resume will happen when user calls "continue"

        if self._is_cancelled(): return

        # 5. CUTTING
        self._job_host.update_job_status(self.job_id, JobStatus.CUTTING, "Cutting and processing clips...", progress_percent=80)
        
        # We don't skip cutting usually because it might be partial or parameters changed?
        # Maybe skip if 'clips_result.json' exists?
        clips_result_path = os.path.join(self.job_dir, "clips_result.json")
        clips_info = []

        if os.path.exists(clips_result_path):
             clips_info = self._load_artifact("clips_result.json")
             print("[INFO] Resuming: Cutting already done")
        else:
            from services.core.tasks_stateless import cut_step
            
            # Define progress callback for FFmpeg pipeline (3-arg: clip_index, total_clips, clip_progress)
            def _on_cut_progress(clip_index, total_clips, clip_progress):
                """Maps per-clip progress to overall job progress 80-95%"""
                clip_weight = 15.0 / max(total_clips, 1)
                completed_weight = clip_index * clip_weight
                current_weight = clip_progress * clip_weight
                job_progress = int(80 + completed_weight + current_weight)
                self._job_host.update_job_status(
                    self.job_id,
                    JobStatus.CUTTING,
                    f"Clip {clip_index+1}/{total_clips} ({job_progress}%)",
                    progress_percent=min(job_progress, 95),
                )
            
            clips_info = cut_step(
                video_path,
                clips_data,
                phrase_timings,
                data, # config for subtitles, hooks, etc
                self.job_id, # Pass job_id for unique folder
                progress_callback=_on_cut_progress,
                check_cancelled=self._is_cancelled
            )
            self._save_artifact("clips_result.json", clips_info)

        # 6. DONE
        meta = self._load_metadata()
        meta["clips"] = clips_info
        if self._meta_store is not None:
            self._meta_store.save_metadata(self.job_id, meta)
        else:
            self._save_artifact("metadata.json", meta)

        elapsed = _time.time() - _pipeline_start
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)
        time_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"
        clip_count = len(clips_info) if clips_info else 0
        done_msg = f"Completed! {clip_count} clips in {time_str}"

        self._job_host.update_job_status(self.job_id, JobStatus.COMPLETE, done_msg, progress_percent=100)

        # Auto-upload to R2 if automation meta requests it
        auto_meta_path = os.path.join(self.job_dir, "automation_meta.json")
        if os.path.exists(auto_meta_path):
            try:
                with open(auto_meta_path, "r", encoding="utf-8") as f:
                    auto_meta = json.load(f)
                if auto_meta.get("params", {}).get("upload_r2"):
                    r2_folder = auto_meta.get("params", {}).get("r2_folder", "clips")
                    print(f"[R2] Auto-uploading clips for job {self.job_id}...")
                    from services.automation.r2_uploader import upload_job_clips
                    # Load clips data from the saved result
                    cr_path = os.path.join(self.job_dir, "clips_result.json")
                    if os.path.exists(cr_path):
                        with open(cr_path, "r", encoding="utf-8") as f:
                            cr_data = json.load(f)
                        clips_list = cr_data if isinstance(cr_data, list) else cr_data.get("clips", [])
                        upload_results = upload_job_clips(self.job_id, clips_list, folder=r2_folder)
                        uploaded = sum(1 for r in upload_results if r["status"] == "uploaded")
                        # Save R2 URLs to automation meta
                        auto_meta["r2_uploads"] = upload_results
                        with open(auto_meta_path, "w", encoding="utf-8") as f:
                            json.dump(auto_meta, f, indent=2)
                        print(f"[R2] Auto-upload done: {uploaded}/{len(clips_list)} clips uploaded")
            except Exception as e:
                print(f"[R2] Auto-upload failed (non-fatal): {e}")

