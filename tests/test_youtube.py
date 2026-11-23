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
