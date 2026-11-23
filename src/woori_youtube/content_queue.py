"""Channel- and content-type scoped production claims; never uploads."""
from sqlalchemy import text
import json
from .content_types import ContentType


class ContentQueue:
    def __init__(self, engine):
        self.engine = engine

    def claim(self, channel: str, content_type: ContentType, worker: str, lease_seconds: int = 14400,
              max_concurrent_jobs: int = 1):
        kind = ContentType(content_type)
        if not channel.strip() or not worker.strip() or lease_seconds < 1 or max_concurrent_jobs < 1:
            raise ValueError("Channel, worker and positive lease are required")
        with self.engine.begin() as conn:
            # Serialize admission per channel; row locks alone do not enforce a global limit.
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:channel, 0))"), {"channel": channel})
            running = conn.execute(text("SELECT count(*) FROM content_plans WHERE channel_id=:channel AND status='running'"),
                                   {"channel": channel}).scalar_one()
            if running >= max_concurrent_jobs:
                return None
            return conn.execute(text("""WITH candidate AS (
                SELECT plan_id FROM content_plans WHERE channel_id=:channel AND content_type=:type
                AND status='planned' ORDER BY created_at,plan_id FOR UPDATE SKIP LOCKED LIMIT 1)
                UPDATE content_plans p SET status='running',stage='claimed',claimed_by=:worker,
                lease_expires_at=now()+make_interval(secs => :lease),updated_at=now(),attempts=attempts+1
                FROM candidate WHERE p.plan_id=candidate.plan_id RETURNING p.*"""),
                {"channel": channel, "type": kind.value, "worker": worker, "lease": lease_seconds}).mappings().first()

    def transition(self, plan_id: str, worker: str, *, status: str, stage: str, error: str | None = None):
        if status not in {"running", "blocked", "ready_for_review", "failed"} or not stage.strip():
            raise ValueError("Invalid state or stage")
        with self.engine.begin() as conn:
            updated = conn.execute(text("""UPDATE content_plans SET status=:status,stage=:stage,error=:error,
                updated_at=now(),lease_expires_at=CASE WHEN :status='running' THEN lease_expires_at ELSE NULL END
                WHERE plan_id=:id AND status='running' AND claimed_by=:worker AND lease_expires_at>now()
                RETURNING plan_id"""),
                {"id": plan_id, "worker": worker, "status": status, "stage": stage, "error": error}).scalar_one_or_none()
            if not updated:
                raise ValueError("Claim is missing, expired, or owned by another worker")

    def recover_expired(self, channel: str) -> int:
        with self.engine.begin() as conn:
            result = conn.execute(text("""UPDATE content_plans SET status='blocked',stage='recovery_review',
                error='Lease expired; inspect artifacts before retry',lease_expires_at=NULL,updated_at=now()
                WHERE channel_id=:channel AND status='running' AND lease_expires_at<=now()"""),
                {"channel": channel})
            return result.rowcount

    def ready_for_review(self, plan_id: str, worker: str, *, script: dict, video_path: str, duration_seconds: float):
        if not video_path or duration_seconds <= 0:
            raise ValueError("A video path and positive duration are required")
        with self.engine.begin() as conn:
            updated = conn.execute(text("""UPDATE content_plans SET status='ready_for_review',stage='editorial_review',
                script=CAST(:script AS JSON),video_path=:video,duration_seconds=:duration,updated_at=now(),
                lease_expires_at=NULL WHERE plan_id=:id AND status='running' AND claimed_by=:worker
                AND lease_expires_at>now() RETURNING plan_id"""),
                {"id": plan_id, "worker": worker, "script": json.dumps(script), "video": video_path,
                 "duration": duration_seconds}).scalar_one_or_none()
            if not updated:
                raise ValueError("Claim is missing, expired, or owned by another worker")

    def retry(self, plan_id: str) -> None:
        with self.engine.begin() as conn:
            updated = conn.execute(text("""UPDATE content_plans SET status='planned',stage='planned',error=NULL,
                claimed_by=NULL,lease_expires_at=NULL,updated_at=now()
                WHERE plan_id=:id AND status IN ('blocked','failed') AND youtube_video_id IS NULL
                RETURNING plan_id"""), {"id": plan_id}).scalar_one_or_none()
            if not updated:
                raise ValueError("Only blocked or failed unpublished plans can be retried")
