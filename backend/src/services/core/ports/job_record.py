"""Stable job view for API and persistence mapping (Liskov-friendly DTO)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class JobRecord:
    job_id: str
    status: str
    progress_message: str
    percentage: Optional[int] = None
    error: Optional[str] = None

    @staticmethod
    def from_metadata_dict(job_id: str, meta: Dict[str, Any]) -> "JobRecord":
        status = str(meta.get("status", "unknown"))
        progress_raw = meta.get("progress_msg") or meta.get("progress") or ""
        progress_message = str(progress_raw) if progress_raw is not None else ""
        pct = meta.get("percentage")
        percentage = int(pct) if pct is not None else None
        err = meta.get("error")
        error = str(err) if err is not None else None
        return JobRecord(
            job_id=job_id,
            status=status,
            progress_message=progress_message,
            percentage=percentage,
            error=error,
        )

    @staticmethod
    def from_sqlite_row(job_id: str, row: Dict[str, Any]) -> "JobRecord":
        jid = str(row.get("job_id", job_id))
        status = str(row.get("status", "unknown"))
        prog = row.get("progress")
        if isinstance(prog, int):
            percentage = prog
            progress_message = ""
        else:
            percentage = None
            progress_message = str(prog or "") if prog is not None else ""
        err = row.get("error")
        md = row.get("metadata")
        if isinstance(md, dict) and not progress_message:
            progress_message = str(md.get("progress") or md.get("progress_msg") or "")
        return JobRecord(
            job_id=jid,
            status=status,
            progress_message=progress_message,
            percentage=percentage,
            error=str(err) if err is not None else None,
        )

    def to_status_api_dict(self) -> Dict[str, Any]:
        """Shape aligned with GET /status/{job_id} and OpenAPI-friendly fields."""
        body: Dict[str, Any] = {
            "job_id": self.job_id,
            "status": self.status,
            "progress": self.progress_message if self.progress_message else (self.percentage or 0),
            "message": self.progress_message,
        }
        if self.percentage is not None:
            body["percentage"] = self.percentage
        if self.error is not None:
            body["error"] = self.error
        return body
