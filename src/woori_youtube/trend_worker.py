"""First production stage: recheck a queued trend and preserve its source leads."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from uuid import UUID

from .production_queue import ProductionQueue
from .trends import collect


def run_once(engine, channel: str, region: str, worker: str, artifacts: Path) -> str | None:
    queue = ProductionQueue(engine)
    job = queue.claim(channel, worker)
    if job is None:
        return None
    job_id = str(UUID(job["job_id"]))
    try:
        trends = collect(engine, channel, region)
        match = next((item for item in trends if item.keyword == job["keyword"]), None)
        if match is None:
            raise ValueError("Queued keyword was absent from the production-time RSS snapshot")
        # A feed link is a research lead, not independently verified evidence.
        path = artifacts / channel / "production" / job_id / "trend-leads.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"job_id": job_id, "event_key": job["event_key"],
                                    "trend": asdict(match),
                                    "period": None, "active": None,
                                    "note": "RSS leads require independent research and verification."},
                                   ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        queue.block(job_id, worker, f"Trend recheck failed: {type(exc).__name__}: {exc}"[:1000])
        raise
    queue.block(job_id, worker, "Trend rechecked; independent research and editorial verification required")
    return job_id
