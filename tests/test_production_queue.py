import os
from contextlib import contextmanager

import pytest

from woori_youtube.production_queue import ProductionQueue


@pytest.mark.skipif(not os.getenv("TEST_POSTGRES_URL"), reason="TEST_POSTGRES_URL not set")
def test_postgres_queue_dedup_claim_ownership_and_recovery():
    from sqlalchemy import create_engine, text
    engine = create_engine(os.environ["TEST_POSTGRES_URL"])
    with engine.connect() as connection:
        transaction = connection.begin()
        class TransactionEngine:
            @contextmanager
            def begin(self):
                yield connection
        queue = ProductionQueue(TransactionEngine())
        try:
            first = queue.enqueue("test-us", "event-a", "one")
            assert queue.enqueue("test-us", "event-a", "alias") == first
            second = queue.enqueue("test-us", "event-b", "two")
            assert first != second
            claim = queue.claim("test-us", "worker-a")
            first, second = claim["job_id"], next(x for x in (first, second) if x != claim["job_id"])
            with pytest.raises(ValueError):
                queue.finish(first, "worker-b")
            queue.finish(first, "worker-a")
            assert queue.claim("test-us", "worker-b")["job_id"] == second
            connection.execute(text("UPDATE production_jobs SET lease_expires_at=now()-interval '1 second' WHERE job_id=:id"), {"id": second})
            assert queue.recover_expired("test-us") == 1
            assert queue.claim("test-us", "worker-c") is None
        finally:
            transaction.rollback()
    engine.dispose()


@pytest.mark.skipif(not os.getenv("TEST_POSTGRES_URL"), reason="TEST_POSTGRES_URL not set")
def test_reviewed_admission_requires_latest_fresh_snapshot_and_records_decision():
    from sqlalchemy import create_engine, text
    engine = create_engine(os.environ["TEST_POSTGRES_URL"])
    with engine.connect() as connection:
        transaction = connection.begin()
        class TransactionEngine:
            @contextmanager
            def begin(self):
                yield connection
        queue = ProductionQueue(TransactionEngine())
        channel = "test-reviewed-admission"
        try:
            collection = connection.execute(text("""INSERT INTO trend_collections
                (channel_id,region,collected_at,success) VALUES (:channel,'US',now(),true) RETURNING id"""),
                {"channel": channel}).scalar_one()
            connection.execute(text("""INSERT INTO trend_observations(collection_id,keyword,news_urls)
                VALUES (:id,'topic','[]')"""), {"id": collection})
            with pytest.raises(ValueError, match="absent"):
                queue.enqueue_reviewed_trend(channel, "other", "event", "reviewed")
            job_id = queue.enqueue_reviewed_trend(channel, "topic", "event", "Verified event identity")
            assert connection.execute(text("SELECT count(*) FROM topic_decisions WHERE channel_id=:channel AND decision='selected'"), {"channel": channel}).scalar_one() == 1
            with pytest.raises(ValueError, match="already"):
                queue.enqueue_reviewed_trend(channel, "topic", "event", "duplicate")
            assert queue.claim(channel, "worker")["job_id"] == job_id
            queue.block(job_id, "worker", "Research required")
            assert queue.claim(channel, "worker") is None
            connection.execute(text("""INSERT INTO trend_collections(channel_id,region,collected_at,success)
                VALUES (:channel,'US',now()+interval '1 second',false)"""), {"channel": channel})
            with pytest.raises(ValueError, match="failed or stale"):
                queue.enqueue_reviewed_trend(channel, "topic", "another", "reviewed")
        finally:
            transaction.rollback()
    engine.dispose()
