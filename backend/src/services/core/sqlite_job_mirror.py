"""Mirror job metadata.json changes into SQLite (Composite persistence leg)."""
from __future__ import annotations

from typing import Any, Dict, Optional


def mirror_create_from_initial_state(job_id: str, state: Dict[str, Any]) -> None:
    """Insert queued job row from initial metadata (idempotent on duplicate)."""
    try:
        from services.core.job_database import job_database

        job_data = state.get("data") or {}
        job_database.create_job(job_id, job_data)
    except Exception:
        pass


def mirror_status_from_metadata(job_id: str, meta: Dict[str, Any]) -> None:
    """UPDATE jobs row from saved metadata.json."""
    try:
        from services.core.job_database import job_database

        status = str(meta.get("status", "unknown"))
        pct = meta.get("percentage")
        progress_int: Optional[int] = int(pct) if pct is not None else None
        err = meta.get("error")
        err_s = str(err) if err is not None else None
        job_database.update_job_status(job_id, status, progress=progress_int, error=err_s)
    except Exception:
        pass
