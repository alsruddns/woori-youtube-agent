"""Run prepared content plans through freshness and render gates, without publishing."""
import json
from pathlib import Path
from uuid import UUID

from .content_production import render_content
from .content_queue import ContentQueue
from .content_types import ContentType, compilation_selection
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
        ranking = job.get("ranking_snapshot") or {}
        if ContentType(kind) == ContentType.TOP5_SHORT and ranking.get("mode", "VERIFIED_RANKING") == "VERIFIED_RANKING":
            raise ValueError("Fresh official 24-hour ranking cannot be verified from RSS")
        if ranking.get("mode") == "VOLUME_BUCKET_ORDERED":
            current_buckets = {trend.keyword: trend.volume_lower_bound for trend in current}
            if any(current_buckets.get(topic["keyword"]) != topic.get("volume_lower_bound") for topic in job["topics"]):
                raise ValueError("Volume buckets changed; replan using the latest collection")
        path = input_root / f"{plan_id}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("topics") != job["topics"] or payload.get("content_type") != job["content_type"]:
            raise ValueError("Prepared input does not match the persisted plan")
        if ContentType(kind) == ContentType.TOP5_SHORT:
            resolved = compilation_selection(payload["topics"], period=payload.get("period"), ranking_basis=payload.get("ranking_basis"))
            if resolved != ranking:
                raise ValueError("Prepared ranking selection does not match the persisted selection")
        queue.transition(plan_id, worker, status="running", stage="rendering")
        result = render_content(kind, payload["topics"], payload["research"], payload["script"],
                                payload["assets"], output_root / plan_id / f"attempt-{job['attempts']}", ffmpeg=ffmpeg,
                                thumbnail_asset=payload.get("thumbnail_asset"), period=payload.get("period"),
                                ranking_basis=payload.get("ranking_basis"), audio_profile=payload.get("audio_profile", "original_preview"))
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
