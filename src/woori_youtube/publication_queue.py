"""Durable private-upload queue. Uncertain outcomes always require inspection."""
import hashlib
from pathlib import Path
from uuid import uuid4
from sqlalchemy import text


def video_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class PublicationQueue:
    def __init__(self, engine):
        self.engine = engine

    def enqueue(self, plan_id: str, *, review_note: str) -> str:
        if not review_note.strip():
            raise ValueError("A completed editorial and rights review note is required")
        with self.engine.begin() as conn:
            plan = conn.execute(text("""SELECT channel_id,status,video_path,youtube_video_id
                FROM content_plans WHERE plan_id=:id FOR UPDATE"""), {"id": plan_id}).mappings().first()
            if not plan or plan["status"] != "ready_for_review" or plan["youtube_video_id"]:
                raise ValueError("Only a reviewed, not-yet-uploaded plan can be queued")
            path = Path(plan["video_path"] or "")
            if not path.is_file():
                raise ValueError("The rendered video is missing")
            result = conn.execute(text("""INSERT INTO publication_jobs
                (publication_id,plan_id,channel_id,review_note,video_sha256)
                VALUES (:id,:plan,:channel,:note,:sha) ON CONFLICT DO NOTHING RETURNING publication_id"""),
                {"id": str(uuid4()), "plan": plan_id, "channel": plan["channel_id"],
                 "note": review_note, "sha": video_sha256(path)}).scalar_one_or_none()
            if not result:
                raise ValueError("A publication job already exists for this plan or reviewed video")
            return result

    def claim(self, channel_id: str, worker: str, lease_seconds: int = 3600):
        if not channel_id.strip() or not worker.strip() or lease_seconds < 1:
            raise ValueError("Channel, worker and positive lease are required")
        with self.engine.begin() as conn:
            return conn.execute(text("""WITH candidate AS (SELECT publication_id FROM publication_jobs
                WHERE channel_id=:channel AND status='pending' ORDER BY created_at,publication_id
                FOR UPDATE SKIP LOCKED LIMIT 1)
                UPDATE publication_jobs j SET status='uploading',claimed_by=:worker,
                lease_expires_at=now()+make_interval(secs => :lease),attempts=attempts+1,updated_at=now()
                FROM candidate WHERE j.publication_id=candidate.publication_id RETURNING j.*"""),
                {"channel": channel_id, "worker": worker, "lease": lease_seconds}).mappings().first()

    def mark_uploaded(self, publication_id: str, worker: str, video_id: str) -> None:
        if not video_id.strip():
            raise ValueError("YouTube video ID is required")
        with self.engine.begin() as conn:
            job = conn.execute(text("""UPDATE publication_jobs SET status='uploaded_unverified',
                youtube_video_id=:video,lease_expires_at=NULL,updated_at=now()
                WHERE publication_id=:id AND status='uploading' AND claimed_by=:worker
                AND lease_expires_at>now() RETURNING plan_id"""),
                {"id": publication_id, "worker": worker, "video": video_id}).scalar_one_or_none()
            if not job:
                raise ValueError("Upload claim is missing or expired; inspect YouTube before retrying")
            updated = conn.execute(text("""UPDATE content_plans SET youtube_video_id=:video,
                status='uploaded_unverified',stage='verify_upload',updated_at=now()
                WHERE plan_id=:plan AND youtube_video_id IS NULL RETURNING plan_id"""),
                {"plan": job, "video": video_id}).scalar_one_or_none()
            if not updated:
                raise ValueError("Plan already has an upload; inspect before retrying")

    def block(self, publication_id: str, worker: str, reason: str) -> None:
        with self.engine.begin() as conn:
            updated = conn.execute(text("""UPDATE publication_jobs SET status='blocked',error=:reason,
                lease_expires_at=NULL,updated_at=now() WHERE publication_id=:id AND status='uploading'
                AND claimed_by=:worker RETURNING publication_id"""),
                {"id": publication_id, "worker": worker, "reason": reason[:1000]}).scalar_one_or_none()
            if not updated:
                raise ValueError("Upload job is not owned by this worker")

    def confirm_private(self, publication_id: str, video_id: str) -> None:
        with self.engine.begin() as conn:
            plan_id = conn.execute(text("""UPDATE publication_jobs SET status='uploaded_private',updated_at=now()
                WHERE publication_id=:id AND status='uploaded_unverified' AND youtube_video_id=:video
                RETURNING plan_id"""), {"id": publication_id, "video": video_id}).scalar_one_or_none()
            if not plan_id:
                raise ValueError("The upload is not awaiting verification")
            conn.execute(text("""UPDATE content_plans SET status='uploaded_private',stage='upload_verified',
                updated_at=now() WHERE plan_id=:plan AND youtube_video_id=:video"""),
                {"plan": plan_id, "video": video_id})

    def recover_expired(self, channel_id: str) -> int:
        with self.engine.begin() as conn:
            return conn.execute(text("""UPDATE publication_jobs SET status='blocked',
                error='Upload outcome uncertain; inspect session and YouTube before retry',
                lease_expires_at=NULL,updated_at=now() WHERE channel_id=:channel AND status='uploading'
                AND lease_expires_at<=now()"""), {"channel": channel_id}).rowcount
