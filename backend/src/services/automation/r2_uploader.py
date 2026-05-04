"""R2 uploader — upload ZenClip output clips to Cloudflare R2.

Uses boto3 S3-compatible API. Reads credentials from r2_config.json
in the backend root directory.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional, List, Dict

_r2_client = None
_r2_config: Optional[dict] = None


def _load_r2_config() -> dict:
    """Load R2 config from r2_config.json in backend root."""
    global _r2_config
    if _r2_config is not None:
        return _r2_config

    # Try multiple possible locations
    candidates = [
        os.path.join(os.path.dirname(__file__), "..", "..", "r2_config.json"),
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "r2_config.json"),
    ]

    for path in candidates:
        path = os.path.normpath(path)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                _r2_config = json.load(f)
            return _r2_config

    raise FileNotFoundError(
        "r2_config.json not found. Create it in backend/ with keys: "
        "r2_endpoint, r2_access_key, r2_secret_key, r2_bucket, r2_public_url"
    )


def get_r2_client():
    """Lazy-init boto3 S3 client for R2."""
    global _r2_client
    if _r2_client is None:
        import boto3
        cfg = _load_r2_config()
        _r2_client = boto3.client(
            "s3",
            endpoint_url=cfg["r2_endpoint"],
            aws_access_key_id=cfg["r2_access_key"],
            aws_secret_access_key=cfg["r2_secret_key"],
            region_name="auto",
        )
    return _r2_client


def upload_file(
    local_path: str,
    key: str,
    content_type: str = "video/mp4",
    folder: str = "clips",
) -> str:
    """Upload a file to R2 and return the public URL.

    Args:
        local_path: Absolute path to the file on disk.
        key: Object key (filename) in R2.
        content_type: MIME type for the upload.
        folder: R2 folder prefix (e.g. "clips", "carousel", "thumbnail").

    Returns:
        Public URL of the uploaded file.
    """
    cfg = _load_r2_config()
    full_key = f"{folder}/{key}" if folder else key

    s3 = get_r2_client()
    with open(local_path, "rb") as f:
        s3.put_object(
            Bucket=cfg["r2_bucket"],
            Key=full_key,
            Body=f,
            ContentType=content_type,
        )

    public_url = f"{cfg['r2_public_url']}/{full_key}"
    return public_url


def upload_job_clips(
    job_id: str,
    clips_result: list,
    folder: str = "clips",
) -> List[Dict]:
    """Upload all clips from a completed job to R2.

    Args:
        job_id: The job UUID.
        clips_result: List of clip dicts from clips_result.json.
        folder: R2 folder prefix.

    Returns:
        List of dicts with upload info (filename, r2_url, file_size).
    """
    results = []
    for clip in clips_result:
        clip_path = clip.get("path", "")
        if not clip_path or not os.path.exists(clip_path):
            results.append({
                "filename": clip.get("topic", "unknown"),
                "status": "skipped",
                "error": "File not found on disk",
            })
            continue

        filename = clip_path.rsplit("/", 1)[-1] if "/" in clip_path else clip_path.rsplit("\\", 1)[-1]
        try:
            r2_url = upload_file(
                local_path=clip_path,
                key=filename,
                content_type="video/mp4",
                folder=folder,
            )
            file_size = os.path.getsize(clip_path)
            results.append({
                "filename": filename,
                "r2_url": r2_url,
                "file_size_bytes": file_size,
                "status": "uploaded",
            })
        except Exception as e:
            results.append({
                "filename": filename,
                "status": "error",
                "error": str(e),
            })

    return results
