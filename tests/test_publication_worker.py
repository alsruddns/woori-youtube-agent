from contextlib import contextmanager
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest

from woori_youtube import publication_worker as worker
from woori_youtube.youtube import PublishBlocked


def test_private_worker_checks_reviewed_hash_and_never_uploads_changed_video(tmp_path, monkeypatch):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"changed")
    actions = []
    class Queue:
        def __init__(self, engine): pass
        def recover_expired(self, channel): return 0
        def claim(self, channel, owner): return {"publication_id": "pub", "plan_id": "plan", "video_sha256": "old"}
        def block(self, *args): actions.append("blocked")
    class Result:
        def mappings(self): return self
        def one(self): return {"content_type": "SINGLE_SHORT", "status": "ready_for_review", "youtube_video_id": None,
                              "video_path": str(video), "script": {"title": "x", "description": "y"}}
    class Engine:
        @contextmanager
        def begin(self):
            class Connection:
                def execute(self, *args): return Result()
            yield Connection()
    monkeypatch.setattr(worker, "PublicationQueue", Queue)
    monkeypatch.setattr(worker, "verify_channel", lambda *args: None)
    monkeypatch.setattr(worker, "upload_video", lambda *args, **kwargs: actions.append("upload"))
    credentials = SimpleNamespace(valid=True, has_scopes=lambda scopes: True)
    with pytest.raises(PublishBlocked, match="differs"):
        worker.run_once(Engine(), "us", "worker", credentials, "channel", ffmpeg="ffmpeg")
    assert actions == ["blocked"]


@pytest.mark.skipif(not os.getenv("TEST_POSTGRES_URL"), reason="TEST_POSTGRES_URL not set")
def test_private_worker_records_success_with_postgres_and_mock_youtube(tmp_path, monkeypatch):
    from sqlalchemy import create_engine, text
    from woori_youtube.publication_queue import PublicationQueue
    engine = create_engine(os.environ["TEST_POSTGRES_URL"])
    with engine.connect() as conn:
        tx = conn.begin()
        class TransactionEngine:
            @contextmanager
            def begin(self): yield conn
        class Response:
            def execute(self):
                return {"items": [{"snippet": {"channelId": "expected"}, "status": {"privacyStatus": "private"}}]}
        class Service:
            def videos(self): return self
            def list(self, **kwargs): return Response()
        try:
            channel, plan = str(uuid4()), str(uuid4())
            collection = conn.execute(text("""INSERT INTO trend_collections(channel_id,region,collected_at,success)
                VALUES (:channel,'US',now(),true) RETURNING id"""), {"channel": channel}).scalar_one()
            video = tmp_path / "video.mp4"
            video.write_bytes(b"local video")
            conn.execute(text("""INSERT INTO content_plans(plan_id,channel_id,content_type,collection_id,
                fingerprint,topics,status,video_path,script) VALUES (:id,:channel,'SINGLE_SHORT',:collection,
                :id,'[]','ready_for_review',:path,'{"title":"test","description":"test"}')"""),
                {"id": plan, "channel": channel, "collection": collection, "path": str(video)})
            db = TransactionEngine()
            PublicationQueue(db).enqueue(plan, review_note="Reviewed for test")
            monkeypatch.setattr(worker, "verify_channel", lambda *args: None)
            monkeypatch.setattr(worker, "validate_video", lambda *args, **kwargs: [])
            monkeypatch.setattr(worker, "validate_video_content", lambda *args, **kwargs: [])
            monkeypatch.setattr(worker, "build", lambda *args, **kwargs: Service())
            def upload(*args, **kwargs):
                assert kwargs["privacy_status"] == "private"
                return "test-video-id"
            monkeypatch.setattr(worker, "upload_video", upload)
            credentials = SimpleNamespace(valid=True, has_scopes=lambda scopes: True)
            assert worker.run_once(db, channel, "worker", credentials, "expected", ffmpeg="ffmpeg") == "test-video-id"
            row = conn.execute(text("SELECT status,youtube_video_id FROM content_plans WHERE plan_id=:id"), {"id": plan}).mappings().one()
            assert row["status"] == "uploaded_private" and row["youtube_video_id"] == "test-video-id"
        finally:
            tx.rollback()
    engine.dispose()


def test_worker_keeps_unverified_id_when_channel_mismatch(tmp_path, monkeypatch):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    actions = []
    class Queue:
        def __init__(self, engine): pass
        def recover_expired(self, channel): return 0
        def claim(self, channel, owner): return {"publication_id": "pub", "plan_id": "plan", "video_sha256": worker.video_sha256(video)}
        def mark_uploaded(self, *args): actions.append("recorded")
        def confirm_private(self, *args): actions.append("confirmed")
        def block(self, *args): actions.append("blocked")
    class Result:
        def mappings(self): return self
        def one(self): return {"content_type": "SINGLE_SHORT", "status": "ready_for_review", "youtube_video_id": None,
                              "video_path": str(video), "script": {"title": "x", "description": "y"}}
    class Engine:
        @contextmanager
        def begin(self):
            class Connection:
                def execute(self, *args): return Result()
            yield Connection()
    class Service:
        def videos(self): return self
        def list(self, **kwargs): return self
        def execute(self): return {"items": [{"snippet": {"channelId": "wrong"}, "status": {"privacyStatus": "private"}}]}
    monkeypatch.setattr(worker, "PublicationQueue", Queue)
    monkeypatch.setattr(worker, "verify_channel", lambda *args: None)
    monkeypatch.setattr(worker, "validate_video", lambda *args, **kwargs: [])
    monkeypatch.setattr(worker, "validate_video_content", lambda *args, **kwargs: [])
    monkeypatch.setattr(worker, "upload_video", lambda *args, **kwargs: "video-id")
    monkeypatch.setattr(worker, "build", lambda *args, **kwargs: Service())
    credentials = SimpleNamespace(valid=True, has_scopes=lambda scopes: True)
    with pytest.raises(PublishBlocked, match="channel or private"):
        worker.run_once(Engine(), "us", "worker", credentials, "expected", ffmpeg="ffmpeg")
    assert actions == ["recorded"]
