"""Record a confirmed YouTube caption track against its existing video plan."""
import hashlib
from pathlib import Path
from sqlalchemy import text


def record_caption(engine, *, caption_id: str, video_id: str, srt: Path, language: str,
                   track_name: str, timing_method: str, status: str) -> None:
    if not all((caption_id, video_id, language, track_name, timing_method, status)) or not srt.is_file():
        raise ValueError("Complete caption details and an existing SRT are required")
    digest = hashlib.sha256(srt.read_bytes()).hexdigest()
    with engine.begin() as conn:
        plan_id = conn.execute(text("SELECT plan_id FROM content_plans WHERE youtube_video_id=:video"),
                               {"video": video_id}).scalar_one_or_none()
        if not plan_id:
            raise ValueError("No content plan is associated with this video")
        conn.execute(text("""INSERT INTO caption_tracks(caption_id,plan_id,video_id,language,track_name,
            srt_path,srt_sha256,timing_method,status) VALUES (:id,:plan,:video,:language,:name,:path,:sha,:timing,:status)
            ON CONFLICT(caption_id) DO NOTHING"""),
            {"id": caption_id, "plan": plan_id, "video": video_id, "language": language, "name": track_name,
             "path": str(srt), "sha": digest, "timing": timing_method, "status": status})
