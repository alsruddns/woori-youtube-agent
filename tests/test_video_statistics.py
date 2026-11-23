import os
from contextlib import contextmanager
from uuid import uuid4

import pytest

from woori_youtube import video_statistics
from woori_youtube.youtube import PublishBlocked


def test_missing_statistics_are_not_fabricated():
    assert video_statistics._count({}, "viewCount") is None
    assert video_statistics._count({"viewCount": "0"}, "viewCount") == 0
    with pytest.raises(ValueError):
        video_statistics._count({"viewCount": "-1"}, "viewCount")


@pytest.mark.skipif(not os.getenv("TEST_POSTGRES_URL"), reason="TEST_POSTGRES_URL not set")
def test_statistics_verify_channel_and_record_only_returned_values(monkeypatch):
    from sqlalchemy import create_engine, text
    engine = create_engine(os.environ["TEST_POSTGRES_URL"])
    with engine.connect() as conn:
        tx = conn.begin()
        class TransactionEngine:
            @contextmanager
            def begin(self): yield conn
            @contextmanager
            def connect(self): yield conn
        class Service:
            channel_id = "expected"
            def videos(self): return self
            def list(self, **kwargs): return self
            def execute(self): return {"items": [{"snippet": {"channelId": self.channel_id}, "statistics": {"viewCount": "3"}}]}
        try:
            channel, plan, video = str(uuid4()), str(uuid4()), str(uuid4())
            collection = conn.execute(text("""INSERT INTO trend_collections(channel_id,region,collected_at,success)
                VALUES (:channel,'US',now(),true) RETURNING id"""), {"channel": channel}).scalar_one()
            conn.execute(text("""INSERT INTO content_plans(plan_id,channel_id,content_type,collection_id,fingerprint,
                topics,youtube_video_id) VALUES (:id,:channel,'SINGLE_SHORT',:collection,:id,'[]',:video)"""),
                {"id": plan, "channel": channel, "collection": collection, "video": video})
            service = Service()
            monkeypatch.setattr(video_statistics, "verify_channel", lambda *args: None)
            monkeypatch.setattr(video_statistics, "build", lambda *args, **kwargs: service)
            result = video_statistics.collect_video_statistics(TransactionEngine(), None, channel=channel,
                                                               expected_channel_id="expected", video_id=video)
            assert result["view_count"] == 3 and result["like_count"] is None
            service.channel_id = "wrong"
            with pytest.raises(PublishBlocked):
                video_statistics.collect_video_statistics(TransactionEngine(), None, channel=channel,
                                                          expected_channel_id="expected", video_id=video)
            assert conn.execute(text("SELECT count(*) FROM video_statistics WHERE video_id=:video"), {"video": video}).scalar_one() == 1
        finally:
            tx.rollback()
    engine.dispose()
