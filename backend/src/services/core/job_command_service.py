"""Application service implementing JobCommandPort (orchestrator + DB list ops)."""
from __future__ import annotations

from typing import Any, Dict, Optional

from services.core.ports.context import JobRequestContext
from services.core.ports.job_record import JobRecord
from services.core.ports.protocols import JobCommandPort


class LegacyJobCommandService(JobCommandPort):
    """Facade over JobManager + JobDatabase until full DI migration completes."""

    def __init__(self, job_manager: Any, job_database: Any) -> None:
        self._jm = job_manager
        self._db = job_database

    def submit_job(
        self,
        job_data: Dict[str, Any],
        priority: int = 5,
        ctx: Optional[JobRequestContext] = None,
    ) -> str:
        return self._jm.submit_job(job_data, priority=priority, ctx=ctx)

    def get_job_record(self, job_id: str) -> Optional[JobRecord]:
        raw = self._jm.get_job(job_id)
        if raw:
            return JobRecord.from_metadata_dict(job_id, raw)
        row = self._db.get_job(job_id)
        if row:
            return JobRecord.from_sqlite_row(job_id, row)
        return None

    def cancel_job(self, job_id: str) -> bool:
        ok = self._jm.cancel_job(job_id)
        if ok:
            try:
                self._db.update_job_status(job_id, "cancelled")
            except Exception:
                pass
        return ok

    def list_jobs(
        self,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        jobs = self._db.list_jobs(status=status, limit=limit, offset=offset)
        return {
            "jobs": jobs,
            "count": len(jobs),
            "filters": {"status": status, "limit": limit, "offset": offset},
        }

    def get_job_stats(self) -> Dict[str, Any]:
        return self._db.get_stats()

    def delete_job_record(self, job_id: str) -> bool:
        if self._jm.get_job(job_id):
            self._jm.cancel_job(job_id)
        return self._db.delete_job(job_id)

    def get_job_metadata(self, job_id: str) -> Optional[Dict[str, Any]]:
        raw = self._jm.get_job(job_id)
        if raw:
            return raw
        row = self._db.get_job(job_id)
        return row

    def resume_pipeline_job(self, job_id: str) -> bool:
        return self._jm.resume_job(job_id)
