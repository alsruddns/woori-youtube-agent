import os
from contextlib import contextmanager
from uuid import uuid4

import pytest

from woori_youtube.publication_queue import PublicationQueue


@pytest.mark.skipif(not os.getenv("TEST_POSTGRES_URL"), reason="TEST_POSTGRES_URL not set")
def test_private_upload_queue_prevents_duplicates_and_records_video(tmp_path):
    from sqlalchemy import create_engine, text
    engine = create_engine(os.environ["TEST_POSTGRES_URL"])
    with engine.connect() as conn:
        tx = conn.begin()
        class TransactionEngine:
            @contextmanager
            def begin(self): yield conn
        try:
            channel, plan = str(uuid4()), str(uuid4())
            collection = conn.execute(text("""INSERT INTO trend_collections(channel_id,region,collected_at,success)
                VALUES (:channel,'US',now(),true) RETURNING id"""), {"channel": channel}).scalar_one()
            video = tmp_path / "video.mp4"
            video.write_bytes(b"local video")
            conn.execute(text("""INSERT INTO content_plans(plan_id,channel_id,content_type,collection_id,
                fingerprint,topics,status,video_path) VALUES (:id,:channel,'SINGLE_SHORT',:collection,:id,'[]',
                'ready_for_review',:path)"""), {"id": plan, "channel": channel, "collection": collection, "path": str(video)})
            queue = PublicationQueue(TransactionEngine())
            with pytest.raises(ValueError, match="review"):
                queue.enqueue(plan, review_note="")
            job = queue.enqueue(plan, review_note="Fact, visuals, and rights reviewed")
            with pytest.raises(ValueError, match="already exists"):
                queue.enqueue(plan, review_note="reviewed")
            second_plan = str(uuid4())
            conn.execute(text("""INSERT INTO content_plans(plan_id,channel_id,content_type,collection_id,
                fingerprint,topics,status,video_path) VALUES (:id,:channel,'SINGLE_SHORT',:collection,:id,'[]',
                'ready_for_review',:path)"""), {"id": second_plan, "channel": channel, "collection": collection, "path": str(video)})
            with pytest.raises(ValueError, match="reviewed video"):
                queue.enqueue(second_plan, review_note="reviewed")
            assert queue.claim(channel, "worker")["publication_id"] == job
            assert queue.claim(channel, "second") is None
            queue.mark_uploaded(job, "worker", "video-id")
            queue.confirm_private(job, "video-id")
            row = conn.execute(text("SELECT status,youtube_video_id FROM content_plans WHERE plan_id=:id"), {"id": plan}).mappings().one()
            assert row["status"] == "uploaded_private" and row["youtube_video_id"] == "video-id"
        finally:
            tx.rollback()
    engine.dispose()


@pytest.mark.skipif(not os.getenv("TEST_POSTGRES_URL"), reason="TEST_POSTGRES_URL not set")
def test_expired_upload_is_blocked_not_retried(tmp_path):
    from sqlalchemy import create_engine, text
    engine = create_engine(os.environ["TEST_POSTGRES_URL"])
    with engine.connect() as conn:
        tx = conn.begin()
        class TransactionEngine:
            @contextmanager
            def begin(self): yield conn
        try:
            channel, plan = str(uuid4()), str(uuid4())
            collection = conn.execute(text("""INSERT INTO trend_collections(channel_id,region,collected_at,success)
                VALUES (:channel,'US',now(),true) RETURNING id"""), {"channel": channel}).scalar_one()
            video = tmp_path / "video.mp4"
            video.write_bytes(b"local video")
            conn.execute(text("""INSERT INTO content_plans(plan_id,channel_id,content_type,collection_id,
                fingerprint,topics,status,video_path) VALUES (:id,:channel,'SINGLE_SHORT',:collection,:id,'[]',
                'ready_for_review',:path)"""), {"id": plan, "channel": channel, "collection": collection, "path": str(video)})
            queue = PublicationQueue(TransactionEngine())
            job = queue.enqueue(plan, review_note="Reviewed")
            queue.claim(channel, "worker")
            conn.execute(text("UPDATE publication_jobs SET lease_expires_at=now()-interval '1 second' WHERE publication_id=:id"), {"id": job})
            assert queue.recover_expired(channel) == 1
            assert queue.claim(channel, "worker") is None
        finally:
            tx.rollback()
    engine.dispose()
