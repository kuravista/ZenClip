"""
SQLite-based job database for persistent job metadata.

Replaces JSON file-based job persistence with SQLite for:
- Better query capabilities
- Atomic transactions
- Concurrent access safety
- Smaller storage footprint
"""
import os
import json
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
from contextlib import contextmanager
import threading


class JobDatabase:
    """
    SQLite database for job metadata.

    Schema:
    - jobs: Main job records
    - job_artifacts: Related artifacts (transcript, analysis, clips)
    - job_events: Event log for debugging
    """

    def __init__(self, db_path: Path):
        """
        Initialize job database.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Jobs table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    progress INTEGER DEFAULT 0,
                    error TEXT,
                    video_path TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    metadata JSON
                )
            ''')

            # Job artifacts table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS job_artifacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    artifact_type TEXT NOT NULL,
                    artifact_path TEXT,
                    artifact_data JSON,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
                )
            ''')

            # Job events table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS job_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    event_data JSON,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
                )
            ''')

            # Create indexes
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_artifacts_job ON job_artifacts(job_id)')

            conn.commit()

    @contextmanager
    def _get_connection(self):
        """Get database connection with proper setup."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    # === Job CRUD Operations ===

    def create_job(self, job_id: str, metadata: Dict) -> None:
        """
        Create a new job record.

        Args:
            job_id: Unique job identifier
            metadata: Job metadata dict
        """
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO jobs (job_id, status, video_path, metadata)
                    VALUES (?, 'queued', ?, ?)
                ''', (
                    job_id,
                    metadata.get('video_path'),
                    json.dumps(metadata)
                ))
                conn.commit()

    def get_job(self, job_id: str) -> Optional[Dict]:
        """
        Get job by ID.

        Args:
            job_id: Job identifier

        Returns:
            Job dict or None
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM jobs WHERE job_id = ?', (job_id,))
            row = cursor.fetchone()

            if row:
                return self._row_to_dict(row)
            return None

    def update_job_status(
        self,
        job_id: str,
        status: str,
        progress: Optional[int] = None,
        error: Optional[str] = None
    ) -> None:
        """
        Update job status.

        Args:
            job_id: Job identifier
            status: New status
            progress: Optional progress value
            error: Optional error message
        """
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                updates = ['status = ?', 'updated_at = CURRENT_TIMESTAMP']
                params = [status]

                if progress is not None:
                    updates.append('progress = ?')
                    params.append(progress)

                if error is not None:
                    updates.append('error = ?')
                    params.append(error)

                if status == 'processing' or status == 'transcribing' or status == 'analyzing' or status == 'cutting':
                    updates.append('started_at = COALESCE(started_at, CURRENT_TIMESTAMP)')

                if status == 'complete' or status == 'error':
                    updates.append('completed_at = CURRENT_TIMESTAMP')

                params.append(job_id)

                cursor.execute(
                    f"UPDATE jobs SET {', '.join(updates)} WHERE job_id = ?",
                    params
                )
                conn.commit()

    def delete_job(self, job_id: str) -> bool:
        """
        Delete a job and its artifacts.

        Args:
            job_id: Job identifier

        Returns:
            True if deleted
        """
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM jobs WHERE job_id = ?', (job_id,))
                deleted = cursor.rowcount > 0
                conn.commit()
                return deleted

    def list_jobs(
        self,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict]:
        """
        List jobs with optional filtering.

        Args:
            status: Filter by status
            limit: Max results
            offset: Result offset

        Returns:
            List of job dicts
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            if status:
                cursor.execute('''
                    SELECT * FROM jobs
                    WHERE status = ?
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                ''', (status, limit, offset))
            else:
                cursor.execute('''
                    SELECT * FROM jobs
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                ''', (limit, offset))

            return [self._row_to_dict(row) for row in cursor.fetchall()]

    # === Artifact Operations ===

    def save_artifact(
        self,
        job_id: str,
        artifact_type: str,
        data: Optional[Dict] = None,
        path: Optional[str] = None
    ) -> None:
        """
        Save a job artifact.

        Args:
            job_id: Job identifier
            artifact_type: Type (transcript, analysis, clips_result)
            data: Artifact data dict
            path: Optional file path
        """
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO job_artifacts (job_id, artifact_type, artifact_path, artifact_data)
                    VALUES (?, ?, ?, ?)
                ''', (job_id, artifact_type, path, json.dumps(data) if data else None))
                conn.commit()

    def get_artifact(self, job_id: str, artifact_type: str) -> Optional[Dict]:
        """
        Get job artifact.

        Args:
            job_id: Job identifier
            artifact_type: Artifact type

        Returns:
            Artifact data or None
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT artifact_data FROM job_artifacts
                WHERE job_id = ? AND artifact_type = ?
            ''', (job_id, artifact_type))
            row = cursor.fetchone()

            if row and row['artifact_data']:
                return json.loads(row['artifact_data'])
            return None

    # === Event Logging ===

    def log_event(self, job_id: str, event_type: str, data: Optional[Dict] = None) -> None:
        """
        Log a job event.

        Args:
            job_id: Job identifier
            event_type: Event type
            data: Optional event data
        """
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO job_events (job_id, event_type, event_data)
                    VALUES (?, ?, ?)
                ''', (job_id, event_type, json.dumps(data) if data else None))
                conn.commit()

    # === Utility Methods ===

    def _row_to_dict(self, row: sqlite3.Row) -> Dict:
        """Convert database row to dict."""
        result = dict(row)

        # Parse JSON fields
        if result.get('metadata'):
            try:
                result['metadata'] = json.loads(result['metadata'])
            except json.JSONDecodeError:
                pass

        return result

    def get_stats(self) -> Dict:
        """Get database statistics."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            stats = {}

            # Count by status
            cursor.execute('''
                SELECT status, COUNT(*) as count
                FROM jobs
                GROUP BY status
            ''')
            stats['by_status'] = {row['status']: row['count'] for row in cursor.fetchall()}

            # Total count
            cursor.execute('SELECT COUNT(*) as total FROM jobs')
            stats['total_jobs'] = cursor.fetchone()['total']

            # Database size
            stats['db_size_bytes'] = os.path.getsize(self.db_path) if self.db_path.exists() else 0

            return stats

    def cleanup_old_jobs(self, days: int = 7) -> int:
        """
        Delete jobs older than specified days.

        Args:
            days: Delete jobs older than this many days

        Returns:
            Number of jobs deleted
        """
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    DELETE FROM jobs
                    WHERE created_at < datetime('now', '-' || ? || ' days')
                ''', (days,))
                deleted = cursor.rowcount
                conn.commit()
                return deleted


def get_job_database() -> JobDatabase:
    """
    Get or create the job database instance.

    Uses environment variables:
    - CLIP_APP_DATA_DIR: App data directory
    - CLIP_JOBS_DB_PATH: Override database path
    """
    db_path = os.environ.get('CLIP_JOBS_DB_PATH')
    if not db_path:
        app_data_dir = os.environ.get('CLIP_APP_DATA_DIR', '.')
        db_path = os.path.join(app_data_dir, 'jobs.db')

    return JobDatabase(Path(db_path))


# Global instance
job_database = get_job_database()
