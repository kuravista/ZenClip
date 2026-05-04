"""Default in-process pipeline execution (PipelineRunner / Open-closed extension point)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from services.core.composite_metadata_persistence import CompositeMetadataPersistence
from services.core.job_status_adapter import ManagerJobOrchestrationAdapter

if TYPE_CHECKING:
    from services.core.job_manager import JobManager


class ThreadPipelineRunner:
    """Runs JobRunner on the current worker thread."""

    def __init__(self, manager: "JobManager") -> None:
        self._mgr = manager

    def run(self, job_id: str, jobs_dir: str) -> None:
        from services.core.job_runner import JobRunner

        control = ManagerJobOrchestrationAdapter(self._mgr)
        meta = CompositeMetadataPersistence(jobs_dir)
        jr = JobRunner(job_id, jobs_dir, job_host=control, metadata_store=meta)
        jr.run()
