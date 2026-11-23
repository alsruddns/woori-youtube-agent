"""Run prepared content plans through freshness and render gates, without publishing."""
import json
from pathlib import Path
from uuid import UUID

from .content_production import render_content
from .content_queue import ContentQueue
from .content_types import ContentType
from .trends import collect


def run_once(engine, channel: str, region: str, kind: ContentType, worker: str,
             input_root: Path, output_root: Path, *, ffmpeg: str) -> str | None:
    queue = ContentQueue(engine)
    queue.recover_expired(channel)
    job = queue.claim(channel, kind, worker)
    if job is None:
        return None
    plan_id = str(UUID(job["plan_id"]))
    try:
        queue.transition(plan_id, worker, status="running", stage="trend_recheck")
        current = collect(engine, channel, region)
        available = {trend.keyword for trend in current}
        if any(topic["keyword"] not in available for topic in job["topics"]):
            raise ValueError("A selected keyword is absent from the fresh RSS snapshot")
        if ContentType(kind) == ContentType.TOP5_SHORT:
            raise ValueError("Fresh official 24-hour ranking cannot be verified from RSS")
        path = input_root / f"{plan_id}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("topics") != job["topics"] or payload.get("content_type") != job["content_type"]:
            raise ValueError("Prepared input does not match the persisted plan")
        queue.transition(plan_id, worker, status="running", stage="rendering")
        result = render_content(kind, payload["topics"], payload["research"], payload["script"],
                                payload["assets"], output_root / plan_id / f"attempt-{job['attempts']}", ffmpeg=ffmpeg,
                                thumbnail_asset=payload.get("thumbnail_asset"))
        queue.ready_for_review(plan_id, worker, script=payload["script"], video_path=result["video"],
                               duration_seconds=result["video_seconds"])
    except Exception as exc:
        try:
            queue.transition(plan_id, worker, status="blocked", stage="review_required",
                             error=f"{type(exc).__name__}: {exc}"[:1000])
        except ValueError:
            pass  # An expired lease requires the recovery path, not another worker's state change.
        raise
    return plan_id
