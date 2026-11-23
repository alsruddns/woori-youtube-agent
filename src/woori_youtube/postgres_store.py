from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .models import JobStatus


class PostgresJobStore:
    """PostgreSQL adapter for the same job ledger contract as JobStore."""

    def __init__(self, url: str):
        try:
            from sqlalchemy import create_engine, text
        except ImportError as exc:
            raise RuntimeError("Install SQLAlchemy and psycopg to use PostgreSQL.") from exc
        self.engine = create_engine(url, pool_pre_ping=True)
        self.text = text

    def initialize(self) -> None:
        statements = [
            "CREATE TABLE IF NOT EXISTS jobs (job_id TEXT PRIMARY KEY, channel_id TEXT NOT NULL, job_date DATE NOT NULL, status TEXT NOT NULL, started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ, attempts INTEGER NOT NULL DEFAULT 0, error TEXT, result_json JSON, UNIQUE(channel_id,job_date))",
            "CREATE TABLE IF NOT EXISTS uploads (upload_id TEXT PRIMARY KEY, channel_id TEXT NOT NULL, job_date DATE NOT NULL, youtube_video_id TEXT NOT NULL, privacy_status TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL, UNIQUE(channel_id,job_date))",
            "CREATE TABLE IF NOT EXISTS audit_events (event_id BIGSERIAL PRIMARY KEY, job_id TEXT, event_type TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL, details_json JSON NOT NULL)",
        ]
        with self.engine.begin() as conn:
            for statement in statements:
                conn.execute(self.text(statement))

    def create_job(self, channel_id: str, job_date: str) -> str:
        job_id, now = str(uuid4()), datetime.now(timezone.utc)
        with self.engine.begin() as conn:
            inserted = conn.execute(self.text("INSERT INTO jobs(job_id,channel_id,job_date,status) VALUES(:id,:channel,CAST(:date AS DATE),:status) ON CONFLICT(channel_id,job_date) DO NOTHING RETURNING job_id"),
                         {"id": job_id, "channel": channel_id, "date": job_date, "status": JobStatus.PENDING.value})
            row = inserted.first()
            actual_id = row[0] if row else conn.execute(self.text("SELECT job_id FROM jobs WHERE channel_id=:channel AND job_date=CAST(:date AS DATE)"), {"channel": channel_id, "date": job_date}).scalar_one()
            if row:
                conn.execute(self.text("INSERT INTO audit_events(job_id,event_type,created_at,details_json) VALUES(:id,'job_created',:now,'{}')"), {"id": actual_id, "now": now})
        return actual_id

    def transition(self, job_id: str, status: JobStatus, *, error: str | None = None, result: dict[str, Any] | None = None) -> None:
        allowed = {JobStatus.PENDING: {JobStatus.RUNNING, JobStatus.BLOCKED, JobStatus.FAILED},
                   JobStatus.RUNNING: {JobStatus.RETRY, JobStatus.BLOCKED, JobStatus.SUCCEEDED, JobStatus.FAILED},
                   JobStatus.RETRY: {JobStatus.RUNNING, JobStatus.FAILED, JobStatus.BLOCKED},
                   JobStatus.BLOCKED: {JobStatus.PENDING}, JobStatus.FAILED: {JobStatus.PENDING}, JobStatus.SUCCEEDED: set()}
        now = datetime.now(timezone.utc)
        with self.engine.begin() as conn:
            row = conn.execute(self.text("SELECT status FROM jobs WHERE job_id=:id FOR UPDATE"), {"id": job_id}).mappings().first()
            if row is None:
                raise KeyError(job_id)
            current = JobStatus(row["status"])
            if status not in allowed[current]:
                raise ValueError(f"Invalid job status transition: {current} -> {status}")
            conn.execute(self.text("UPDATE jobs SET status=:status, started_at=CASE WHEN :running THEN :now WHEN :pending THEN NULL ELSE started_at END, finished_at=CASE WHEN :finished THEN :now WHEN :pending THEN NULL ELSE finished_at END, attempts=attempts+CASE WHEN :running THEN 1 ELSE 0 END, error=:error, result_json=COALESCE(CAST(:result AS JSON),result_json) WHERE job_id=:id"),
                         {"status": status.value, "running": status == JobStatus.RUNNING, "pending": status == JobStatus.PENDING, "finished": status in {JobStatus.BLOCKED, JobStatus.FAILED, JobStatus.SUCCEEDED}, "now": now, "error": error, "result": json.dumps(result) if result is not None else None, "id": job_id})
            conn.execute(self.text("INSERT INTO audit_events(job_id,event_type,created_at,details_json) VALUES(:id,:event,:now,CAST(:details AS JSON))"),
                         {"id": job_id, "event": f"status:{status.value}", "now": now, "details": json.dumps({"error": error})})

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.execute(self.text("SELECT * FROM jobs WHERE job_id=:id"), {"id": job_id}).mappings().first()
        return dict(row) if row else None

    def get_job_for_date(self, channel_id: str, job_date: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.execute(self.text("SELECT * FROM jobs WHERE channel_id=:channel AND job_date=CAST(:date AS DATE)"), {"channel": channel_id, "date": job_date}).mappings().first()
        return dict(row) if row else None

    def list_jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            rows = conn.execute(self.text("SELECT * FROM jobs ORDER BY job_date DESC LIMIT :limit"), {"limit": limit}).mappings().all()
        return [dict(row) for row in rows]

    def record_upload(self, channel_id: str, job_date: str, video_id: str, privacy_status: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(self.text("INSERT INTO uploads(upload_id,channel_id,job_date,youtube_video_id,privacy_status,created_at) VALUES(:id,:channel,CAST(:date AS DATE),:video,:privacy,:now)"),
                         {"id": str(uuid4()), "channel": channel_id, "date": job_date, "video": video_id, "privacy": privacy_status, "now": datetime.now(timezone.utc)})

    def has_upload(self, channel_id: str, job_date: str) -> bool:
        with self.engine.connect() as conn:
            return conn.execute(self.text("SELECT 1 FROM uploads WHERE channel_id=:channel AND job_date=CAST(:date AS DATE)"), {"channel": channel_id, "date": job_date}).first() is not None

    def recover_interrupted(self) -> int:
        now = datetime.now(timezone.utc)
        with self.engine.begin() as conn:
            result = conn.execute(self.text("UPDATE jobs SET status='retry',finished_at=:now,error='Recovered after process interruption' WHERE status='running'"), {"now": now})
        return result.rowcount or 0
