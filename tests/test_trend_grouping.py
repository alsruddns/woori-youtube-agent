import os
from contextlib import contextmanager
from uuid import uuid4

import pytest

from woori_youtube.trend_grouping import candidate_groups, canonical_url, save_latest_groups


def test_shared_urls_are_candidates_not_confirmed_events():
    rows = [
        {"keyword": "A", "news_urls": ["https://news.example/a?utm_source=x"]},
        {"keyword": "B", "news_urls": ["https://news.example/a", "https://news.example/b"]},
        {"keyword": "C", "news_urls": ["https://news.example/b"]},
        {"keyword": "Unrelated", "news_urls": ["https://other.example/a"]},
    ]
    groups = candidate_groups(rows)
    assert len(groups) == 1 and groups[0]["keywords"] == ["A", "B", "C"]
    assert groups[0]["review_status"] == "unreviewed"
    assert len(groups[0]["shared_urls"]) == 2


def test_invalid_or_untrusted_urls_do_not_create_groups():
    assert canonical_url("https://user:password@example.com/a") is None
    assert canonical_url("https://[invalid") is None
    assert candidate_groups([{"keyword": "A", "news_urls": ["http://example.com/a"]},
                             {"keyword": "B", "news_urls": ["http://example.com/a"]}]) == []


@pytest.mark.skipif(not os.getenv("TEST_POSTGRES_URL"), reason="TEST_POSTGRES_URL not set")
def test_group_candidates_are_persisted_idempotently():
    from sqlalchemy import create_engine, text
    engine = create_engine(os.environ["TEST_POSTGRES_URL"])
    with engine.connect() as conn:
        tx = conn.begin()
        class TransactionEngine:
            @contextmanager
            def begin(self): yield conn
        try:
            channel = str(uuid4())
            collection = conn.execute(text("""INSERT INTO trend_collections(channel_id,region,collected_at,success)
                VALUES (:channel,'US',now(),true) RETURNING id"""), {"channel": channel}).scalar_one()
            for keyword in ("alpha", "beta"):
                conn.execute(text("""INSERT INTO trend_observations(collection_id,keyword,news_urls)
                    VALUES (:id,:keyword,'["https://example.com/story"]')"""), {"id": collection, "keyword": keyword})
            assert len(save_latest_groups(TransactionEngine(), channel)[1]) == 1
            assert len(save_latest_groups(TransactionEngine(), channel)[1]) == 1
            assert conn.execute(text("SELECT count(*) FROM trend_group_candidates WHERE collection_id=:id"),
                                {"id": collection}).scalar_one() == 1
        finally:
            tx.rollback()
    engine.dispose()
