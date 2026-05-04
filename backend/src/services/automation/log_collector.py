from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import List, Optional


class LogCollector:
    """Collects structured log entries for an automation job.

    Logs are kept in memory and periodically flushed to
    jobs_data/{job_id}/automation_logs.json on disk.
    """

    def __init__(self, job_id: str, jobs_dir: str = "jobs_data"):
        self.job_id = job_id
        self.jobs_dir = jobs_dir
        self._logs: List[dict] = []
        self._load_existing()

    def _log_path(self) -> str:
        return os.path.join(self.jobs_dir, self.job_id, "automation_logs.json")

    def _load_existing(self) -> None:
        path = self._log_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self._logs = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._logs = []

    def log(self, stage: str, message: str, level: str = "info") -> dict:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stage": stage,
            "level": level,
            "message": message,
        }
        self._logs.append(entry)
        return entry

    def log_from_metadata(self, status: str, progress_percent: int, message: str) -> dict:
        """Create a log entry from a metadata status update."""
        level = "error" if status == "error" else "info"
        return self.log(stage=status, message=message, level=level)

    def get_logs(self) -> List[dict]:
        return list(self._logs)

    def save(self) -> None:
        path = self._log_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._logs, f, indent=2, ensure_ascii=False)
