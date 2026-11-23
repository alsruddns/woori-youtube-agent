from datetime import datetime, timezone

import pytest

from woori_youtube.youtube import PublishBlocked, upload_video


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
