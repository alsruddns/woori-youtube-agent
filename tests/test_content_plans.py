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
