"""
Optional multiprocess pipeline runner (Phase 7 placeholder).

Today this delegates to ThreadPipelineRunner. Swap implementation when profiling
shows CPU-bound stages benefit from a separate process and serialization is solved.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from utils.logger import log

if TYPE_CHECKING:
    from services.core.job_manager import JobManager


class MultiprocessPipelineRunnerStub:
    def __init__(self, manager: "JobManager") -> None:
        self._mgr = manager

    def run(self, job_id: str, jobs_dir: str) -> None:
        log.info(
            "MultiprocessPipelineRunnerStub: delegating to thread runner (no separate process yet)",
            module="PipelineRunner",
        )
        from services.core.thread_pipeline_runner import ThreadPipelineRunner

        ThreadPipelineRunner(self._mgr).run(job_id, jobs_dir)
