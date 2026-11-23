from datetime import datetime, timezone

import pytest

from woori_youtube.youtube import PublishBlocked, upload_video, upload_caption_track


def test_public_upload_is_blocked_until_preflight_flag(tmp_path):
    with pytest.raises(PublishBlocked):
        upload_video(tmp_path / "video.mp4", {"title": "x", "description": "y"}, None, privacy_status="public")


def test_public_upload_preflight_flag_opens_next_gate(tmp_path):
    with pytest.raises(FileNotFoundError):
        upload_video(tmp_path / "video.mp4", {"title": "x", "description": "y"}, None,
                     privacy_status="public", public_preflight_passed=True)


def test_scheduled_publish_requires_future_aware_time(tmp_path):
    with pytest.raises(ValueError):
        upload_video(tmp_path / "video.mp4", {"title": "x", "description": "y"}, None,
                     privacy_status="private", publish_at=datetime.now(timezone.utc),
                     public_preflight_passed=True)


def test_completed_upload_is_reused_and_changed_video_is_blocked(tmp_path, monkeypatch):
    from google.auth.transport import requests
    class Response:
        def __init__(self, status, headers=None, payload=None):
            self.status_code, self.headers, self.payload = status, headers or {}, payload or {}
        def raise_for_status(self): pass
        def json(self): return self.payload
    class Session:
        posts = 0
        def __init__(self, credentials): pass
        def post(self, *args, **kwargs):
            Session.posts += 1
            return Response(200, {"Location": "https://example.com/session"})
        def put(self, url, **kwargs):
            if kwargs["headers"]["Content-Length"] == "0":
                return Response(308)
            return Response(200, payload={"id": "video-id"})
    monkeypatch.setattr(requests, "AuthorizedSession", Session)
    path = tmp_path / "video.mp4"
    path.write_bytes(b"video")
    metadata = {"title": "title", "description": "description"}
    assert upload_video(path, metadata, None) == "video-id"
    assert upload_video(path, metadata, None) == "video-id"
    assert Session.posts == 1
    path.write_bytes(b"other")
    with pytest.raises(PublishBlocked, match="does not match"):
        upload_video(path, metadata, None)


def test_missing_chunk_acknowledgement_blocks_instead_of_assuming_success(tmp_path, monkeypatch):
    from google.auth.transport import requests
    class Response:
        status_code = 308
        headers = {}
        def raise_for_status(self): pass
    class Session:
        def __init__(self, credentials): pass
        def post(self, *args, **kwargs):
            response = Response()
            response.headers = {"Location": "https://example.com/session"}
            return response
        def put(self, *args, **kwargs): return Response()
    monkeypatch.setattr(requests, "AuthorizedSession", Session)
    path = tmp_path / "video.mp4"
    path.write_bytes(b"video")
    with pytest.raises(PublishBlocked, match="did not advance"):
        upload_video(path, {"title": "title", "description": "description"}, None)


def test_caption_upload_requires_review_and_additional_scope(tmp_path):
    srt = tmp_path / "caption.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:02,000\nHello\n", encoding="utf-8")
    with pytest.raises(PublishBlocked, match="timing"):
        upload_caption_track("video", srt, None, "channel")
    class Credentials:
        def has_scopes(self, scopes): return False
    with pytest.raises(PublishBlocked, match="force-ssl"):
        upload_caption_track("video", srt, Credentials(), "channel", timing_reviewed=True)


def test_caption_upload_checks_channel_and_existing_tracks(tmp_path, monkeypatch):
    import googleapiclient.discovery
    from woori_youtube import youtube as module
    srt = tmp_path / "caption.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:02,000\nHello\n", encoding="utf-8")
    class Credentials:
        def has_scopes(self, scopes): return True
    class Request:
        def __init__(self, result): self.result = result
        def execute(self): return self.result
    class Service:
        existing = False
        inserts = 0
        def videos(self): return self
        def captions(self): return self
        def list(self, **kwargs):
            if "id" in kwargs:
                return Request({"items": [{"snippet": {"channelId": "channel"}}]})
            return Request({"items": [{"snippet": {"language": "en", "name": "English"}}] if self.existing else []})
        def insert(self, **kwargs):
            self.inserts += 1
            return Request({"id": "caption-id"})
    service = Service()
    monkeypatch.setattr(module, "verify_channel", lambda *args: None)
    monkeypatch.setattr(googleapiclient.discovery, "build", lambda *args, **kwargs: service)
    assert upload_caption_track("video", srt, Credentials(), "channel", timing_reviewed=True) == "caption-id"
    service.existing = True
    with pytest.raises(PublishBlocked, match="already exists"):
        upload_caption_track("video", srt, Credentials(), "channel", timing_reviewed=True)
    assert service.inserts == 1
