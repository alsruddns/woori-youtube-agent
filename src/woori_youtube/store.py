from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .models import JobStatus


class JobStore:
    """Durable local job/duplicate ledger. SQLite is the zero-config dev mode."""

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY, channel_id TEXT NOT NULL, job_date TEXT NOT NULL,
                    status TEXT NOT NULL, started_at TEXT, finished_at TEXT,
                    attempts INTEGER NOT NULL DEFAULT 0, error TEXT, result_json TEXT,
                    UNIQUE(channel_id, job_date)
                );
                CREATE TABLE IF NOT EXISTS uploads (
                    upload_id TEXT PRIMARY KEY, channel_id TEXT NOT NULL, job_date TEXT NOT NULL,
                    youtube_video_id TEXT NOT NULL, privacy_status TEXT NOT NULL,
                    created_at TEXT NOT NULL, UNIQUE(channel_id, job_date)
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT, event_type TEXT NOT NULL,
                    created_at TEXT NOT NULL, details_json TEXT NOT NULL
                );
            """)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def create_job(self, channel_id: str, job_date: str) -> str:
        job_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute("INSERT OR IGNORE INTO jobs(job_id, channel_id, job_date, status) VALUES(?,?,?,?)",
                         (job_id, channel_id, job_date, JobStatus.PENDING.value))
            row = conn.execute("SELECT job_id FROM jobs WHERE channel_id=? AND job_date=?", (channel_id, job_date)).fetchone()
            actual_id = row["job_id"]
            if actual_id == job_id:
                conn.execute("INSERT INTO audit_events(job_id,event_type,created_at,details_json) VALUES(?,?,?,?)",
                             (job_id, "job_created", now, "{}"))
        return actual_id

    def transition(self, job_id: str, status: JobStatus, *, error: str | None = None, result: dict[str, Any] | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            row = conn.execute("SELECT status FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            current = JobStatus(row["status"])
            allowed = {
                JobStatus.PENDING: {JobStatus.RUNNING, JobStatus.BLOCKED, JobStatus.FAILED},
                JobStatus.RUNNING: {JobStatus.RETRY, JobStatus.BLOCKED, JobStatus.SUCCEEDED, JobStatus.FAILED},
                JobStatus.RETRY: {JobStatus.RUNNING, JobStatus.FAILED, JobStatus.BLOCKED},
                JobStatus.BLOCKED: {JobStatus.PENDING},
                JobStatus.FAILED: {JobStatus.PENDING},
                JobStatus.SUCCEEDED: set(),
            }
            if status not in allowed[current]:
                raise ValueError(f"Invalid job status transition: {current} -> {status}")
            started = now if status == JobStatus.RUNNING else None
            finished = now if status in {JobStatus.BLOCKED, JobStatus.FAILED, JobStatus.SUCCEEDED} else None
            conn.execute("UPDATE jobs SET status=?, started_at=CASE WHEN ? THEN ? WHEN ? THEN NULL ELSE started_at END, finished_at=CASE WHEN ? THEN ? WHEN ? THEN NULL ELSE finished_at END, attempts=attempts+?, error=?, result_json=COALESCE(?,result_json) WHERE job_id=?",
                         (status.value, status == JobStatus.RUNNING, started, status == JobStatus.PENDING,
                          status in {JobStatus.BLOCKED, JobStatus.FAILED, JobStatus.SUCCEEDED}, finished,
                          status == JobStatus.PENDING, int(status == JobStatus.RUNNING), error,
                          json.dumps(result) if result is not None else None, job_id))
            conn.execute("INSERT INTO audit_events(job_id,event_type,created_at,details_json) VALUES(?,?,?,?)",
                         (job_id, f"status:{status.value}", now, json.dumps({"error": error})))

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        return dict(row) if row else None

    def get_job_for_date(self, channel_id: str, job_date: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE channel_id=? AND job_date=?", (channel_id, job_date)).fetchone()
        return dict(row) if row else None

    def list_jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM jobs ORDER BY rowid DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    def record_upload(self, channel_id: str, job_date: str, video_id: str, privacy_status: str) -> None:
        with self._connect() as conn:
            conn.execute("INSERT INTO uploads(upload_id,channel_id,job_date,youtube_video_id,privacy_status,created_at) VALUES(?,?,?,?,?,?)",
                         (str(uuid4()), channel_id, job_date, video_id, privacy_status, datetime.now(timezone.utc).isoformat()))

    def has_upload(self, channel_id: str, job_date: str) -> bool:
        with self._connect() as conn:
            return conn.execute("SELECT 1 FROM uploads WHERE channel_id=? AND job_date=?", (channel_id, job_date)).fetchone() is not None

    def recover_interrupted(self) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            result = conn.execute("UPDATE jobs SET status=?, finished_at=?, error=? WHERE status=?",
                                  (JobStatus.RETRY.value, now, "Recovered after process interruption", JobStatus.RUNNING.value))
            count = result.rowcount
            rows = conn.execute("SELECT job_id FROM jobs WHERE status=? AND error=?", (JobStatus.RETRY.value, "Recovered after process interruption")).fetchall()
            for row in rows:
                conn.execute("INSERT INTO audit_events(job_id,event_type,created_at,details_json) VALUES(?,?,?,?)",
                             (row["job_id"], "crash_recovery", now, "{}"))
        return count
