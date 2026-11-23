from __future__ import annotations

import json
import logging
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .channels import Channel, load_channels
from .config import settings
from .ingest import validate_research
from .media import create_thumbnail, render_video, synthesize_scenes, validate_video
from .models import JobStatus
from .pipeline import PipelineBlocked, run_research
from .script import run_codex, script_prompt, validate_script
from .store import JobStore
from .youtube import PublishBlocked, authorize, upload_thumbnail, upload_video, verify_channel

logger = logging.getLogger("woori_youtube")


def _store():
    from .api import get_store
    return get_store()


def _scheduled_publish_time(channel: Channel, run_date: date) -> datetime:
    zone = ZoneInfo(channel.timezone)
    local = datetime.combine(run_date + timedelta(days=1), time(settings.publish_hour, settings.publish_minute), tzinfo=zone)
    return local.astimezone(timezone.utc)


def run_daily(channel_id: str = "us-economy", run_date: date | None = None) -> str:
    catalog = load_channels(settings.channels_file)
    channel = catalog.get(channel_id)
    if channel is None or not channel.enabled:
        raise PipelineBlocked(f"Channel is missing or disabled: {channel_id}")
    run_date = run_date or datetime.now(ZoneInfo(channel.timezone)).date()
    store = _store()
    if store.has_upload(channel_id, run_date.isoformat()):
        raise PipelineBlocked(f"An upload already exists for {channel_id} on {run_date}.")
    job_id = store.create_job(channel_id, run_date.isoformat())
    existing = store.get_job(job_id)
    if existing and existing["status"] == JobStatus.SUCCEEDED:
        raise PipelineBlocked(f"A successful job already exists for {channel_id} on {run_date}.")
    if existing and existing["status"] == JobStatus.RUNNING:
        raise PipelineBlocked(f"A job is already running for {channel_id} on {run_date}.")
    if existing and existing["status"] in {JobStatus.FAILED.value, JobStatus.BLOCKED.value, JobStatus.RETRY.value}:
        store.transition(job_id, JobStatus.PENDING)
    store.transition(job_id, JobStatus.RUNNING)
    artifact_dir = settings.artifacts_dir / channel_id / run_date.isoformat()
    try:
        if not settings.codex_enabled:
            raise PipelineBlocked("Codex execution is disabled. Complete the local Codex CLI setup and set CODEX_ENABLED=true.")
        research = run_research(channel, run_date, settings.artifacts_dir)
        errors = validate_research(research, min_sources=2, require_recent=True)
        if errors:
            raise PipelineBlocked("Research gate blocked the run: " + "; ".join(errors))
        raw = run_codex(script_prompt(research, channel.locale, channel.language_name, channel.target_minutes, channel.disclaimer),
                        artifact_dir / "script.json", command=settings.codex_command,
                        timeout=settings.codex_timeout_seconds)
        errors = validate_script(raw, research, target_minutes=channel.target_minutes,
                                 require_categories={item.category for item in research.items if item.category in channel.categories},
                                 disclaimer=channel.disclaimer)
        (artifact_dir / "script.validation.json").write_text(json.dumps({"passed": not errors, "errors": errors}, indent=2), encoding="utf-8")
        if errors:
            raise PipelineBlocked("Script verification blocked the run: " + "; ".join(errors))
        audio_files = synthesize_scenes(raw["scenes"], artifact_dir / "audio", voice=channel.tts_voice,
                                        language_code=channel.tts_language_code, engine=channel.tts_engine)
        video_path = render_video(raw, audio_files, artifact_dir / "final.mp4", ffmpeg=settings.ffmpeg_bin,
                                  width=settings.video_width, height=settings.video_height)
        media_errors = validate_video(video_path, ffmpeg=settings.ffmpeg_bin,
                                      minimum_seconds=channel.target_minutes * 60 * 0.9)
        if media_errors:
            raise PipelineBlocked("Video quality gate blocked the run: " + "; ".join(media_errors))
        thumbnail = create_thumbnail(raw["title"], artifact_dir / "thumbnail.jpg")
        result = {"video": str(video_path), "thumbnail": str(thumbnail), "research_items": len(research.items),
                  "script_version": 1, "verified": True, "uploaded": False}
        if settings.youtube_enabled:
            if (settings.youtube_privacy_status == "public" or settings.youtube_schedule_enabled) and not settings.youtube_public_preflight_passed:
                raise PublishBlocked("Complete a controlled public-upload preflight in YouTube Studio before enabling public or scheduled uploads.")
            credentials = authorize(settings.youtube_client_secrets_file, settings.youtube_token_file)
            verify_channel(credentials, settings.youtube_channel_id)
            video_id = upload_video(video_path, raw, credentials, privacy_status=settings.youtube_privacy_status,
                                    publish_at=_scheduled_publish_time(channel, run_date) if settings.youtube_schedule_enabled else None,
                                    public_preflight_passed=settings.youtube_public_preflight_passed)
            store.record_upload(channel_id, run_date.isoformat(), video_id, settings.youtube_privacy_status)
            upload_thumbnail(video_id, thumbnail, credentials)
            result.update({"youtube_video_id": video_id, "uploaded": True})
        store.transition(job_id, JobStatus.SUCCEEDED, result=result)
        return job_id
    except PipelineBlocked as exc:
        store.transition(job_id, JobStatus.BLOCKED, error=str(exc))
        logger.error("Job %s blocked: %s", job_id, exc)
        raise
    except PublishBlocked as exc:
        store.transition(job_id, JobStatus.BLOCKED, error=str(exc))
        logger.error("Job %s requires publishing review: %s", job_id, exc)
        raise
    except Exception as exc:
        store.transition(job_id, JobStatus.FAILED, error=f"{type(exc).__name__}: {exc}")
        logger.exception("Job %s failed", job_id)
        raise


if __name__ == "__main__":
    import sys
    Path("data").mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, filename="data/runner.log", encoding="utf-8")
    try:
        run_daily()
    except (PipelineBlocked, PublishBlocked):
        # Validation/configuration blocks are recorded and should not trigger blind Scheduler retries.
        sys.exit(0)
    except Exception:
        sys.exit(1)
