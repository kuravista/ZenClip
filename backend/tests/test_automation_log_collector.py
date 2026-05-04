import json
import os
import time
import tempfile
import pytest
from services.automation.log_collector import LogCollector


class TestLogCollector:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.job_id = "test-job-123"
        self.jobs_dir = self.tmpdir
        self.collector = LogCollector(self.job_id, self.jobs_dir)

    def test_initial_log_entry(self):
        self.collector.log("preparing", "Job submitted")
        logs = self.collector.get_logs()
        assert len(logs) == 1
        assert logs[0]["stage"] == "preparing"
        assert logs[0]["message"] == "Job submitted"
        assert logs[0]["level"] == "info"

    def test_multiple_entries(self):
        self.collector.log("preparing", "Downloading...")
        self.collector.log("transcribing", "Starting ASR")
        self.collector.log("complete", "Done")
        logs = self.collector.get_logs()
        assert len(logs) == 3

    def test_persist_and_reload(self):
        self.collector.log("preparing", "Test entry")
        self.collector.save()

        collector2 = LogCollector(self.job_id, self.jobs_dir)
        logs = collector2.get_logs()
        assert len(logs) == 1
        assert logs[0]["message"] == "Test entry"

    def test_error_level(self):
        self.collector.log("analyzing", "LLM failed", level="error")
        logs = self.collector.get_logs()
        assert logs[0]["level"] == "error"

    def test_timestamp_format(self):
        self.collector.log("preparing", "Test")
        logs = self.collector.get_logs()
        assert "T" in logs[0]["timestamp"]

    def test_from_metadata_change(self):
        self.collector.log_from_metadata(
            status="preparing",
            progress_percent=10,
            message="Downloading video..."
        )
        logs = self.collector.get_logs()
        assert logs[0]["stage"] == "preparing"
        assert logs[0]["message"] == "Downloading video..."

    def test_no_duplicate_stage_entries(self):
        self.collector.log_from_metadata("preparing", 10, "Working...")
        self.collector.log_from_metadata("preparing", 15, "Working...")
        logs = self.collector.get_logs()
        assert len(logs) == 2

    def test_empty_logs_on_new_job(self):
        logs = self.collector.get_logs()
        assert logs == []
