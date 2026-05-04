"""Artifact locations (local disk today; object storage later)."""
from __future__ import annotations

import os
from typing import Protocol, runtime_checkable


@runtime_checkable
class ArtifactStorePort(Protocol):
    def job_root(self, job_id: str) -> str:
        """Root directory for all artifacts of one job."""
        ...


class LocalFilesystemArtifactStore:
    def __init__(self, jobs_dir: str) -> None:
        self._jobs_dir = jobs_dir

    def job_root(self, job_id: str) -> str:
        return os.path.join(self._jobs_dir, job_id)
