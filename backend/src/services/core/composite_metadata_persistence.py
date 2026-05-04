"""Composite: JSON canonical store + SQLite mirror for list/query (Liskov-friendly)."""
from __future__ import annotations

from typing import Any, Dict, Optional

from services.core.json_metadata_store import JsonJobMetadataStore
from services.core.sqlite_job_mirror import mirror_create_from_initial_state, mirror_status_from_metadata


class CompositeMetadataPersistence:
    """Implements JobPersistencePort; every save updates SQLite when possible."""

    def __init__(self, jobs_dir: str):
        self._json = JsonJobMetadataStore(jobs_dir)

    def load_metadata(self, job_id: str) -> Optional[Dict[str, Any]]:
        return self._json.load_metadata(job_id)

    def save_metadata(self, job_id: str, data: Dict[str, Any]) -> None:
        self._json.save_metadata(job_id, data)
        mirror_status_from_metadata(job_id, data)

    def save_initial_job(self, job_id: str, initial_state: Dict[str, Any]) -> None:
        """First write for a new job: JSON + SQLite INSERT."""
        self._json.save_metadata(job_id, initial_state)
        mirror_create_from_initial_state(job_id, initial_state)
