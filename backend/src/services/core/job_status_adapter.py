"""Adapters from JobManager to narrow ports (Dependency Inversion)."""
from __future__ import annotations

from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from services.core.job_manager import JobManager


class ManagerJobOrchestrationAdapter:
    """JobRunnerHostPort backed by a JobManager instance (not the global singleton in tests)."""

    def __init__(self, manager: "JobManager") -> None:
        self._m = manager

    def update_job_status(
        self,
        job_id: str,
        status: Any,
        progress_msg: Optional[str] = None,
        error_msg: Optional[str] = None,
        progress_percent: Optional[int] = None,
    ) -> None:
        self._m.update_job_status(
            job_id, status, progress_msg=progress_msg, error_msg=error_msg, progress_percent=progress_percent
        )

    def update_job_data(self, job_id: str, updates: Dict[str, Any]) -> bool:
        return self._m.update_job_data(job_id, updates)
