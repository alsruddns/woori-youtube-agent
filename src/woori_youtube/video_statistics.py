"""Collect only available YouTube Data API statistics, not estimated analytics."""
from googleapiclient.discovery import build
from sqlalchemy import text
from .youtube import PublishBlocked, verify_channel


def _count(stats: dict, key: str) -> int | None:
    if key not in stats:
        return None
    value = stats[key]
    if not isinstance(value, str) or not value.isascii() or not value.isdecimal():
        raise ValueError(f"Invalid YouTube statistic: {key}")
    return int(value)


def collect_video_statistics(engine, credentials, *, channel: str, expected_channel_id: str, video_id: str) -> dict:
    if not channel.strip() or not video_id.strip():
        raise ValueError("Channel and video ID are required")
    with engine.connect() as conn:
        plan = conn.execute(text("""SELECT plan_id FROM content_plans
            WHERE channel_id=:channel AND youtube_video_id=:video"""),
            {"channel": channel, "video": video_id}).scalar_one_or_none()
    if not plan:
        raise ValueError("Video is not associated with this channel's content plan")
    verify_channel(credentials, expected_channel_id)
    items = build("youtube", "v3", credentials=credentials).videos().list(
        part="snippet,statistics", id=video_id).execute().get("items", [])
    if len(items) != 1 or items[0].get("snippet", {}).get("channelId") != expected_channel_id:
        raise PublishBlocked("Video does not belong to the configured channel")
    stats = items[0].get("statistics")
    if not isinstance(stats, dict):
        raise ValueError("YouTube did not return video statistics")
    values = {"view_count": _count(stats, "viewCount"), "like_count": _count(stats, "likeCount"),
              "comment_count": _count(stats, "commentCount")}
    with engine.begin() as conn:
        row = conn.execute(text("""INSERT INTO video_statistics(plan_id,video_id,view_count,like_count,comment_count)
            VALUES (:plan,:video,:view_count,:like_count,:comment_count) RETURNING collected_at"""),
            {"plan": plan, "video": video_id, **values}).scalar_one()
    return {"video_id": video_id, **values, "collected_at": row.isoformat()}
