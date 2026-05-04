"""In-process priority queue for job IDs (local JobQueuePort implementation)."""
from __future__ import annotations

import time
from queue import PriorityQueue
from typing import Any, Optional


class LocalPriorityJobQueue:
    """Tuple (priority, timestamp, job_id); lower priority number = higher precedence."""

    def __init__(self) -> None:
        self._q: PriorityQueue = PriorityQueue()

    def enqueue(self, job_id: str, priority: float = 5.0) -> None:
        self._q.put((priority, time.time(), job_id))

    def blocking_dequeue(self) -> Any:
        return self._q.get()

    def task_done(self) -> None:
        self._q.task_done()

    def put_stop(self) -> None:
        self._q.put(None)

    def get_stop_sentinel(self) -> Any:
        return None
