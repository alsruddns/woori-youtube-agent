import os
from contextlib import contextmanager
from uuid import uuid4

import pytest

from woori_youtube.caption_store import record_caption


@pytest.mark.skipif(not os.getenv("TEST_POSTGRES_URL"), reason="TEST_POSTGRES_URL not set")
def test_caption_record_is_idempotent_and_matches_video(tmp_path):
    from sqlalchemy import create_engine, text
    engine = create_engine(os.environ["TEST_POSTGRES_URL"])
    with engine.connect() as conn:
        tx = conn.begin()
        class TransactionEngine:
            @contextmanager
            def begin(self): yield conn
        try:
            plan_id, video_id, caption_id = (str(uuid4()) for _ in range(3))
            collection = conn.execute(text("""INSERT INTO trend_collections(channel_id,region,collected_at,success)
                VALUES ('test','US',now(),true) RETURNING id""")).scalar_one()
            conn.execute(text("""INSERT INTO content_plans(plan_id,channel_id,content_type,collection_id,
                fingerprint,topics,youtube_video_id) VALUES (:id,'test','SINGLE_SHORT',:collection,:id,'[]',:video)"""),
                {"id": plan_id, "collection": collection, "video": video_id})
            srt = tmp_path / "captions.srt"
            srt.write_text("test", encoding="utf-8")
            kwargs = dict(caption_id=caption_id, video_id=video_id, srt=srt, language="en",
                          track_name="English", timing_method="reviewed", status="serving")
            record_caption(TransactionEngine(), **kwargs)
            record_caption(TransactionEngine(), **kwargs)
            assert conn.execute(text("SELECT count(*) FROM caption_tracks WHERE caption_id=:id"),
                                {"id": caption_id}).scalar_one() == 1
        finally:
            tx.rollback()
    engine.dispose()
