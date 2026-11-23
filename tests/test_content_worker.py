import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from woori_youtube import content_worker
from woori_youtube.content_types import ContentType


def test_worker_rechecks_and_marks_review_with_actual_video_duration(tmp_path, monkeypatch):
    plan_id = str(uuid4())
    topics = [{"event_key": "event", "keyword": "topic"}]
    calls = []
    class Queue:
        def __init__(self, engine): pass
        def recover_expired(self, channel): return 0
        def claim(self, channel, kind, worker):
            return {"plan_id": plan_id, "topics": topics, "content_type": "SINGLE_SHORT", "attempts": 2}
        def transition(self, *args, **kwargs): calls.append(("transition", kwargs))
        def ready_for_review(self, *args, **kwargs): calls.append(("ready", kwargs))
    monkeypatch.setattr(content_worker, "ContentQueue", Queue)
    monkeypatch.setattr(content_worker, "collect", lambda *args: [SimpleNamespace(keyword="topic")])
    def render(kind, selected, research, script, assets, output, **kwargs):
        assert output.name == "attempt-2"
        return {"video": "file.mp4", "narration_seconds": 30, "video_seconds": 32}
    monkeypatch.setattr(content_worker, "render_content", render)
    (tmp_path / f"{plan_id}.json").write_text(json.dumps({"content_type": "SINGLE_SHORT", "topics": topics,
        "research": {}, "script": {}, "assets": []}), encoding="utf-8")
    assert content_worker.run_once(None, "us", "US", ContentType.SINGLE_SHORT, "worker", tmp_path, tmp_path, ffmpeg="ffmpeg") == plan_id
    assert calls[-1][0] == "ready" and calls[-1][1]["duration_seconds"] == 32


def test_worker_blocks_stale_keyword_without_rendering(tmp_path, monkeypatch):
    calls = []
    class Queue:
        def __init__(self, engine): pass
        def recover_expired(self, channel): return 0
        def claim(self, channel, kind, worker):
            return {"plan_id": str(uuid4()), "topics": [{"keyword": "old"}], "attempts": 1}
        def transition(self, *args, **kwargs): calls.append(kwargs)
    monkeypatch.setattr(content_worker, "ContentQueue", Queue)
    monkeypatch.setattr(content_worker, "collect", lambda *args: [SimpleNamespace(keyword="new")])
    with pytest.raises(ValueError, match="absent"):
        content_worker.run_once(None, "us", "US", ContentType.SINGLE_SHORT, "worker", tmp_path, tmp_path, ffmpeg="ffmpeg")
    assert calls[-1]["status"] == "blocked"
