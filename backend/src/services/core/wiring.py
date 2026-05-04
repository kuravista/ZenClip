"""Composition root helpers (Dependency Inversion entry)."""
from __future__ import annotations

from services.core.job_command_service import LegacyJobCommandService
from services.core.job_database import job_database
from services.core.job_manager import job_manager
from services.core.ports.protocols import JobCommandPort


def build_default_job_command_port() -> JobCommandPort:
    return LegacyJobCommandService(job_manager, job_database)
