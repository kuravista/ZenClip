import json
import os
import time
import tempfile
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
from fastapi import FastAPI

from routers.automation import router as automation_router


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(automation_router, prefix="/api/v1")
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def mock_job_manager():
    with patch("routers.automation.job_manager") as mock:
        mock.submit_job.return_value = "test-job-id-123"
        mock.get_job_status.return_value = {
            "id": "test-job-id-123",
            "status": "queued",
            "progress": "Waiting in queue...",
            "percentage": 0,
            "data": {"url": "https://youtube.com/watch?v=abc"},
            "created_at": time.time(),
            "last_updated": time.time(),
        }
        mock.update_job_status = MagicMock()
        mock.cancel_job.return_value = True
        yield mock


@pytest.fixture
def mock_job_database():
    with patch("routers.automation.job_database") as mock:
        mock.get_job.return_value = None
        mock.list_jobs.return_value = []
        mock.get_stats.return_value = {"total_jobs": 0, "by_status": {"queued": 0, "processing": 0}}
        yield mock


VALID_URL = "https://youtube.com/watch?v=dQw4w9WgXcQ"


class TestSubmitEndpoint:
    def test_submit_success(self, client, mock_job_manager, mock_job_database):
        resp = client.post("/api/v1/clip", json={"url": VALID_URL})
        assert resp.status_code == 202
        data = resp.json()
        assert data["success"] is True
        assert data["job_id"] == "test-job-id-123"
        assert "/api/v1/jobs/" in data["status_url"]
        mock_job_manager.submit_job.assert_called_once()

    def test_submit_calls_bridge(self, client, mock_job_manager, mock_job_database):
        resp = client.post("/api/v1/clip", json={
            "url": VALID_URL,
            "aspect_ratio": "16:9",
            "max_clips": 10,
        })
        assert resp.status_code == 202
        call_args = mock_job_manager.submit_job.call_args
        job_data = call_args[0][0]
        assert job_data["url"] == VALID_URL
        assert job_data["video_aspect"] == "16:9"
        assert job_data["num_clips"] == 10
        assert job_data["stop_for_review"] is False

    def test_submit_missing_url(self, client, mock_job_manager, mock_job_database):
        resp = client.post("/api/v1/clip", json={})
        assert resp.status_code == 422

    def test_submit_invalid_url(self, client, mock_job_manager, mock_job_database):
        resp = client.post("/api/v1/clip", json={"url": "https://example.com"})
        assert resp.status_code == 422

    def test_submit_with_webhook(self, client, mock_job_manager, mock_job_database):
        resp = client.post("/api/v1/clip", json={
            "url": VALID_URL,
            "webhook_url": "https://example.com/hook"
        })
        assert resp.status_code == 202


class TestStatusEndpoint:
    def test_status_found(self, client, mock_job_manager, mock_job_database, tmp_path):
        jobs_dir = str(tmp_path)
        job_id = "test-job-123"
        os.makedirs(os.path.join(jobs_dir, job_id), exist_ok=True)

        meta = {
            "id": job_id,
            "status": "cutting",
            "percentage": 85,
            "progress": "Cutting clip 3 of 5...",
            "data": {"url": VALID_URL},
            "created_at": time.time(),
            "last_updated": time.time(),
        }
        with open(os.path.join(jobs_dir, job_id, "metadata.json"), "w") as f:
            json.dump(meta, f)

        with patch("routers.automation._get_jobs_dir", return_value=jobs_dir):
            resp = client.get(f"/api/v1/jobs/{job_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == job_id
        assert data["status"] == "cutting"
        assert data["progress"] == 85

    def test_status_not_found(self, client, mock_job_manager, mock_job_database):
        resp = client.get("/api/v1/jobs/nonexistent-id")
        assert resp.status_code == 404


class TestCancelEndpoint:
    def test_cancel_success(self, client, mock_job_manager, mock_job_database):
        resp = client.post("/api/v1/jobs/test-job-id-123/cancel")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_cancel_not_found(self, client, mock_job_manager, mock_job_database):
        mock_job_manager.cancel_job.return_value = False
        resp = client.post("/api/v1/jobs/nonexistent/cancel")
        assert resp.status_code == 404


class TestPipelineInfoEndpoint:
    def test_pipeline_info(self, client, mock_job_manager, mock_job_database):
        resp = client.get("/api/v1/pipelines")
        assert resp.status_code == 200
        data = resp.json()
        assert "stages" in data
        assert "defaults" in data
        assert "supported" in data
