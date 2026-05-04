"""FastAPI dependencies (composition root wiring)."""
from __future__ import annotations

from fastapi import Request

from services.core.ports.protocols import JobCommandPort


def get_job_commands(request: Request) -> JobCommandPort:
    return request.app.state.job_commands
