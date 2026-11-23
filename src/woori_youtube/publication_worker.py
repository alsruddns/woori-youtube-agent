"""Execute a separately reviewed publication job as a private upload only."""
from pathlib import Path

from googleapiclient.discovery import build
from sqlalchemy import text

from .content_types import ContentType, SPECS
from .media import validate_video, validate_video_content
from .publication_queue import PublicationQueue, video_sha256
from .youtube import PublishBlocked, upload_video, verify_channel


def run_once(engine, channel_id: str, worker: str, credentials, expected_channel_id: str, *, ffmpeg: str):
    if not credentials or not credentials.valid or not credentials.has_scopes(["https://www.googleapis.com/auth/youtube.upload"]):
        raise PublishBlocked("Valid YouTube upload credentials are required")
    verify_channel(credentials, expected_channel_id)
    queue = PublicationQueue(engine)
    queue.recover_expired(channel_id)
    job = queue.claim(channel_id, worker)
    if not job:
        return None
    publication_id = job["publication_id"]
    try:
        with engine.begin() as conn:
            plan = conn.execute(text("""SELECT content_type,script,video_path,youtube_video_id,status
                FROM content_plans WHERE plan_id=:id AND channel_id=:channel"""),
                {"id": job["plan_id"], "channel": channel_id}).mappings().one()
        if plan["youtube_video_id"] or plan["status"] != "ready_for_review":
            raise PublishBlocked("Plan is no longer eligible for a new upload")
        video = Path(plan["video_path"] or "")
        if not video.is_file() or video_sha256(video) != job["video_sha256"]:
            raise PublishBlocked("Video differs from the reviewed file")
        spec = SPECS[ContentType(plan["content_type"])]
        errors = validate_video(video, ffmpeg=ffmpeg, minimum_seconds=spec.min_seconds,
                                maximum_seconds=spec.max_seconds, width=spec.width, height=spec.height)
        if not errors:
            errors = validate_video_content(video, ffmpeg=ffmpeg)
        if errors:
            raise PublishBlocked("Media gate: " + "; ".join(errors))
        if not isinstance(plan["script"], dict) or not plan["script"].get("title") or not plan["script"].get("description"):
            raise PublishBlocked("Reviewed title and description are missing")
        video_id = upload_video(video, plan["script"], credentials, privacy_status="private")
        # Save ID before any further network call; session file remains a second recovery record.
        queue.mark_uploaded(publication_id, worker, video_id)
    except Exception as exc:
        try:
            queue.block(publication_id, worker, f"{type(exc).__name__}: inspect upload session and YouTube before retry")
        except ValueError:
            pass
        raise
    response = build("youtube", "v3", credentials=credentials).videos().list(
        part="snippet,status", id=video_id).execute().get("items", [])
    if (len(response) != 1 or response[0].get("snippet", {}).get("channelId") != expected_channel_id
            or response[0].get("status", {}).get("privacyStatus") != "private"):
        raise PublishBlocked("Upload ID recorded, but channel or private status could not be verified")
    queue.confirm_private(publication_id, video_id)
    return video_id
