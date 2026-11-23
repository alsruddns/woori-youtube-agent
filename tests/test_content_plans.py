import os
from contextlib import contextmanager
from uuid import uuid4

import pytest

from woori_youtube.content_plans import create_plan
from woori_youtube.content_types import ContentType


@pytest.mark.skipif(not os.getenv("TEST_POSTGRES_URL"), reason="TEST_POSTGRES_URL not set")
def test_type_scoped_dedup_and_ranking_snapshot():
    from sqlalchemy import create_engine, text
    engine = create_engine(os.environ["TEST_POSTGRES_URL"])
    with engine.connect() as conn:
        tx = conn.begin()
        class TransactionEngine:
            @contextmanager
            def begin(self):
                yield conn
        channel = str(uuid4())
        try:
            collection = conn.execute(text("""INSERT INTO trend_collections
                (channel_id,region,collected_at,success) VALUES (:channel,'US',now(),true) RETURNING id"""),
                {"channel": channel}).scalar_one()
            topics = [{"event_key": f"e{i}", "keyword": f"k{i}", "rank": i,
                       "rank_evidence_url": "https://trends.google.com/"} for i in range(1, 6)]
            for topic in topics:
                conn.execute(text("""INSERT INTO trend_observations(collection_id,keyword,news_urls)
                    VALUES (:collection,:keyword,'[]')"""), {"collection": collection, "keyword": topic["keyword"]})
            db = TransactionEngine()
            create_plan(db, channel, ContentType.SINGLE_SHORT, collection, topics[:1])
            create_plan(db, channel, ContentType.MAIN_NEWS, collection, topics)
            top_id = create_plan(db, channel, ContentType.TOP5_SHORT, collection, topics,
                                 period="past_24_hours", ranking_basis="official_distinct")
            snapshot = conn.execute(text("SELECT ranking_snapshot FROM content_plans WHERE plan_id=:id"),
                                    {"id": top_id}).scalar_one()
            assert [item["rank"] for item in snapshot["items"]] == [5, 4, 3, 2, 1]
            with pytest.raises(ValueError, match="Equivalent"):
                create_plan(db, channel, ContentType.SINGLE_SHORT, collection, topics[:1])
        finally:
            tx.rollback()
    engine.dispose()


@pytest.mark.skipif(not os.getenv("TEST_POSTGRES_URL"), reason="TEST_POSTGRES_URL not set")
def test_queue_claim_isolation_lease_recovery_and_retry():
    from sqlalchemy import create_engine, text
    from woori_youtube.content_queue import ContentQueue
    engine = create_engine(os.environ["TEST_POSTGRES_URL"])
    with engine.connect() as conn:
        tx = conn.begin()
        class TransactionEngine:
            @contextmanager
            def begin(self):
                yield conn
        channel = str(uuid4())
        try:
            collection = conn.execute(text("""INSERT INTO trend_collections
                (channel_id,region,collected_at,success) VALUES (:channel,'US',now(),true) RETURNING id"""),
                {"channel": channel}).scalar_one()
            conn.execute(text("INSERT INTO trend_observations(collection_id,keyword,news_urls) VALUES (:id,'test','[]')"), {"id": collection})
            conn.execute(text("INSERT INTO trend_observations(collection_id,keyword,news_urls) VALUES (:id,'test2','[]')"), {"id": collection})
            db = TransactionEngine()
            plan = create_plan(db, channel, ContentType.SINGLE_SHORT, collection, [{"event_key": "event", "keyword": "test"}])
            create_plan(db, channel, ContentType.SINGLE_SHORT, collection, [{"event_key": "event2", "keyword": "test2"}])
            conn.execute(text("UPDATE content_plans SET created_at=now()-interval '1 second' WHERE plan_id=:id"), {"id": plan})
            queue = ContentQueue(db)
            assert queue.claim(channel, ContentType.MAIN_NEWS, "worker") is None
            assert queue.claim(channel, ContentType.SINGLE_SHORT, "worker")["plan_id"] == plan
            assert queue.claim(channel, ContentType.SINGLE_SHORT, "other") is None
            with pytest.raises(ValueError, match="owned"):
                queue.transition(plan, "other", status="blocked", stage="review")
            conn.execute(text("UPDATE content_plans SET lease_expires_at=now()-interval '1 second' WHERE plan_id=:id"), {"id": plan})
            assert queue.recover_expired(channel) == 1
            other = queue.claim(channel, ContentType.SINGLE_SHORT, "worker")
            assert other and other["plan_id"] != plan
            queue.transition(other["plan_id"], "worker", status="blocked", stage="review")
            queue.retry(plan)
            assert queue.claim(channel, ContentType.SINGLE_SHORT, "worker")["plan_id"] == plan
            queue.ready_for_review(plan, "worker", script={"title": "test"}, video_path="test.mp4", duration_seconds=34)
            with pytest.raises(ValueError, match="blocked or failed"):
                queue.retry(plan)
        finally:
            tx.rollback()
    engine.dispose()
