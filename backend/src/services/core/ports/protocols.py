"""SOLID ports: narrow protocols for commands, persistence, queue, pipeline, status updates."""
from __future__ import annotations

from typing import Any, Dict, Optional, Protocol, runtime_checkable

from services.core.ports.context import JobRequestContext
from services.core.ports.job_record import JobRecord


@runtime_checkable
class JobRunnerHostPort(Protocol):
    """Narrow surface JobRunner needs from JobManager (status + data patches)."""

    def update_job_status(
        self,
        job_id: str,
        status: Any,
        progress_msg: Optional[str] = None,
        error_msg: Optional[str] = None,
        progress_percent: Optional[int] = None,
    ) -> None:
        ...

    def update_job_data(self, job_id: str, updates: Dict[str, Any]) -> bool:
        ...


@runtime_checkable
class JobPersistencePort(Protocol):
    def load_metadata(self, job_id: str) -> Optional[Dict[str, Any]]:
        ...

    def save_metadata(self, job_id: str, data: Dict[str, Any]) -> None:
        ...


@runtime_checkable
class JobQueuePort(Protocol):
    def enqueue(self, job_id: str, priority: float = 5.0) -> None:
        ...

    def blocking_dequeue(self) -> Any:
        ...

    def task_done(self) -> None:
        ...

    def put_stop(self) -> None:
        ...

    def get_stop_sentinel(self) -> Any:
        """Value used to stop worker loop (implementation-specific)."""
        ...


@runtime_checkable
class PipelineRunner(Protocol):
    def run(self, job_id: str, jobs_dir: str) -> None:
        ...


@runtime_checkable
class JobCommandPort(Protocol):
    """HTTP-facing job operations (router depends only on this)."""

    def submit_job(
        self,
        job_data: Dict[str, Any],
        priority: int = 5,
        ctx: Optional[JobRequestContext] = None,
    ) -> str:
        ...

    def get_job_record(self, job_id: str) -> Optional[JobRecord]:
        ...

    def cancel_job(self, job_id: str) -> bool:
        ...

    def list_jobs(
        self,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        ...

    def get_job_stats(self) -> Dict[str, Any]:
        ...

    def delete_job_record(self, job_id: str) -> bool:
        ...

    def get_job_metadata(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Raw metadata dict (transcript flow, debugging); prefer JobRecord for API responses."""
        ...

    def resume_pipeline_job(self, job_id: str) -> bool:
        """Re-queue a paused/failed job."""
        ...
