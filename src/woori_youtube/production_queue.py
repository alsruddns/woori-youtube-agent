"""Durable queue primitives; an event key must come from verified editorial review."""
from __future__ import annotations
from uuid import uuid4
from sqlalchemy import text


class ProductionQueue:
    def __init__(self, engine):
        self.engine = engine

    def enqueue(self, channel_id: str, event_key: str, keyword: str) -> str:
        if not all(x.strip() for x in (channel_id, event_key, keyword)):
            raise ValueError("channel, verified event key and keyword are required")
        with self.engine.begin() as conn:
            inserted = conn.execute(text("""INSERT INTO production_jobs(job_id, channel_id, event_key, keyword)
                VALUES (:id,:channel,:event,:keyword) ON CONFLICT(channel_id,event_key) DO NOTHING RETURNING job_id"""),
                {"id": str(uuid4()), "channel": channel_id, "event": event_key, "keyword": keyword}).scalar_one_or_none()
            if inserted:
                return inserted
            return conn.execute(text("SELECT job_id FROM production_jobs WHERE channel_id=:channel AND event_key=:event"),
                                {"channel": channel_id, "event": event_key}).scalar_one()

    def claim(self, channel_id: str, worker_id: str, lease_seconds: int = 3600):
        if not worker_id.strip() or lease_seconds < 1:
            raise ValueError("worker and positive lease duration required")
        with self.engine.begin() as conn:
            return conn.execute(text("""WITH candidate AS (
                SELECT job_id FROM production_jobs WHERE channel_id=:channel AND status='pending'
                ORDER BY created_at,job_id FOR UPDATE SKIP LOCKED LIMIT 1)
                UPDATE production_jobs j SET status='running',claimed_by=:worker,
                lease_expires_at=now()+make_interval(secs => :lease),updated_at=now(),attempts=attempts+1
                FROM candidate WHERE j.job_id=candidate.job_id RETURNING j.*"""),
                {"channel": channel_id, "worker": worker_id, "lease": lease_seconds}).mappings().first()

    def finish(self, job_id: str, worker_id: str, *, error: str | None = None):
        with self.engine.begin() as conn:
            updated = conn.execute(text("""UPDATE production_jobs SET status=:status, error=:error,
                updated_at=now(),lease_expires_at=NULL WHERE job_id=:id AND status='running'
                AND claimed_by=:worker AND lease_expires_at > now() RETURNING job_id"""),
                {"status": "failed" if error else "succeeded", "error": error, "id": job_id, "worker": worker_id}).scalar_one_or_none()
            if not updated:
                raise ValueError("job is not owned by this worker or its lease expired")

    def recover_expired(self, channel_id: str) -> int:
        # Never blindly retry a job which might have reached an external upload.
        with self.engine.begin() as conn:
            result = conn.execute(text("""UPDATE production_jobs SET status='blocked',
                error='Lease expired; inspect artifacts and publication before retry',updated_at=now(),
                lease_expires_at=NULL WHERE channel_id=:channel AND status='running' AND lease_expires_at <= now()"""),
                {"channel": channel_id})
            return result.rowcount
