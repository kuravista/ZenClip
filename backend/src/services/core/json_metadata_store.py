"""JSON file persistence for per-job metadata.json (Single Responsibility)."""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

from utils.logger import log


class JsonJobMetadataStore:
    """Read/write `metadata.json` under `{jobs_dir}/{job_id}/`."""

    def __init__(self, jobs_dir: str):
        self.jobs_dir = jobs_dir

    def load_metadata(self, job_id: str) -> Optional[Dict[str, Any]]:
        path = os.path.join(self.jobs_dir, job_id, "metadata.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def save_metadata(self, job_id: str, data: Dict[str, Any]) -> None:
        path = os.path.join(self.jobs_dir, job_id, "metadata.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        temp_path = path + ".tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(temp_path, path)
        except Exception as e:
            log.warn(f"Failed to save metadata for {job_id}: {e}", module="JsonJobMetadataStore")
