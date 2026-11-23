import json
from uuid import uuid4

import pytest

from woori_youtube import trend_worker
from woori_youtube.trends import Trend


def test_worker_rechecks_and_blocks_before_research(tmp_path, monkeypatch):
    job_id = str(uuid4())
    calls = []
    class Queue:
        def __init__(self, engine): pass
        def claim(self, channel, worker):
            return {"job_id": job_id, "keyword": "topic", "event_key": "event"}
        def block(self, job, worker, reason): calls.append((job, reason))
    monkeypatch.setattr(trend_worker, "ProductionQueue", Queue)
    monkeypatch.setattr(trend_worker, "collect", lambda *args: [Trend("topic", "1000+", 1000, ["https://example.com"], None)])
    assert trend_worker.run_once(None, "us", "US", "worker", tmp_path) == job_id
    leads = json.loads((tmp_path / "us" / "production" / job_id / "trend-leads.json").read_text(encoding="utf-8"))
    assert leads["period"] is None and leads["active"] is None
    assert "research" in calls[0][1]


def test_worker_blocks_if_keyword_disappears(tmp_path, monkeypatch):
    calls = []
    class Queue:
        def __init__(self, engine): pass
        def claim(self, channel, worker):
            return {"job_id": str(uuid4()), "keyword": "topic", "event_key": "event"}
        def block(self, job, worker, reason): calls.append(reason)
    monkeypatch.setattr(trend_worker, "ProductionQueue", Queue)
    monkeypatch.setattr(trend_worker, "collect", lambda *args: [])
    with pytest.raises(ValueError, match="absent"):
        trend_worker.run_once(None, "us", "US", "worker", tmp_path)
    assert "recheck failed" in calls[0]
