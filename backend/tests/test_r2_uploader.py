import sys
import json
import os
import time
import tempfile
import pytest
from unittest.mock import patch, MagicMock

# Add src to path
src_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "src")
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from services.automation.r2_uploader import upload_file, upload_job_clips, _load_r2_config


class TestLoadConfig:
    def test_loads_config_file(self):
        """Config loads from r2_config.json."""
        cfg = _load_r2_config()
        assert "r2_endpoint" in cfg
        assert "r2_access_key" in cfg
        assert "r2_secret_key" in cfg
        assert "r2_bucket" in cfg
        assert "r2_public_url" in cfg

    def test_bucket_is_ayomain(self):
        cfg = _load_r2_config()
        assert cfg["r2_bucket"] == "ayomain-contents"


class TestUploadFile:
    def test_upload_returns_public_url(self):
        """Upload returns R2 public URL."""
        # Create a dummy file
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"fake-video-content")
            tmp_path = f.name

        try:
            url = upload_file(tmp_path, "test_clip.mp4", folder="clips")
            assert "pub-" in url
            assert "r2.dev/clips/test_clip.mp4" in url
        finally:
            os.unlink(tmp_path)

    def test_upload_with_custom_folder(self):
        """Upload respects custom folder prefix."""
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"test")
            tmp_path = f.name

        try:
            url = upload_file(tmp_path, "my_clip.mp4", folder="custom")
            assert "r2.dev/custom/my_clip.mp4" in url
        finally:
            os.unlink(tmp_path)


class TestUploadJobClips:
    def test_upload_multiple_clips(self):
        """Upload all clips from a job."""
        # Create temp files
        files = []
        for i in range(2):
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False, prefix=f"clip_{i}_") as f:
                f.write(b"video-data")
                files.append(f.name)

        try:
            clips = [
                {"path": files[0], "topic": "Clip 1"},
                {"path": files[1], "topic": "Clip 2"},
            ]
            results = upload_job_clips("test-job", clips, folder="clips")
            assert len(results) == 2
            assert all(r["status"] == "uploaded" for r in results)
            assert all("r2_url" in r for r in results)
        finally:
            for f in files:
                os.unlink(f)

    def test_skips_missing_files(self):
        """Clips with missing files are skipped gracefully."""
        clips = [
            {"path": "/nonexistent/file.mp4", "topic": "Ghost clip"},
        ]
        results = upload_job_clips("test-job", clips)
        assert len(results) == 1
        assert results[0]["status"] == "skipped"
