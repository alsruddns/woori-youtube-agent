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
