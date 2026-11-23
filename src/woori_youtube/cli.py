from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from .channels import load_channels
from .config import settings
from .ingest import validate_research
from .pipeline import run_research
from .store import JobStore


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="woori-youtube")
    sub = parser.add_subparsers(dest="command", required=True)
    research = sub.add_parser("research")
    research.add_argument("--channel", default="us-economy")
    research.add_argument("--date", default=date.today().isoformat())
    trends = sub.add_parser("trends")
    trends.add_argument("--channel", default="us-economy")
    trends.add_argument("--region", default="US")
    grouping = sub.add_parser("trend-groups")
    grouping.add_argument("--channel", default="us-economy")
    sub.add_parser("youtube-auth")
    sub.add_parser("youtube-caption-auth")
    caption_upload = sub.add_parser("youtube-caption-upload")
    caption_upload.add_argument("--video-id", required=True)
    caption_upload.add_argument("--srt", required=True, type=Path)
    caption_upload.add_argument("--timing-reviewed", action="store_true", required=True)
    caption_upload.add_argument("--name", default="English reviewed")
    stats = sub.add_parser("youtube-collect-stats")
    stats.add_argument("--channel", default="us-economy")
    stats.add_argument("--video-id", required=True)
    admission = sub.add_parser("enqueue-reviewed-trend")
    admission.add_argument("--channel", default="us-economy")
    admission.add_argument("--keyword", required=True)
    admission.add_argument("--event-key", required=True)
    admission.add_argument("--reason", required=True)
    worker = sub.add_parser("trend-worker-once")
    worker.add_argument("--channel", default="us-economy")
    worker.add_argument("--worker", required=True)
    event_script = sub.add_parser("event-script")
    event_script.add_argument("--research", required=True, type=Path)
    event_script.add_argument("--output", required=True, type=Path)
    event_render = sub.add_parser("event-render")
    event_render.add_argument("--research", required=True, type=Path)
    event_render.add_argument("--script", required=True, type=Path)
    event_render.add_argument("--assets", required=True, type=Path)
    event_render.add_argument("--output-dir", required=True, type=Path)
    content_script = sub.add_parser("content-script")
    content_script.add_argument("--input", required=True, type=Path)
    content_script.add_argument("--output", required=True, type=Path)
    content_render = sub.add_parser("content-render")
    content_render.add_argument("--input", required=True, type=Path)
    content_render.add_argument("--script", required=True, type=Path)
    content_render.add_argument("--assets", required=True, type=Path)
    content_render.add_argument("--output-dir", required=True, type=Path)
    content_render.add_argument("--thumbnail-asset", type=Path)
    content_render.add_argument("--audio-profile", choices=["original_preview", "off"], default="original_preview")
    content_plan = sub.add_parser("content-plan")
    content_plan.add_argument("--channel", default="us-economy")
    content_plan.add_argument("--collection-id", required=True, type=int)
    content_plan.add_argument("--input", required=True, type=Path)
    content_worker = sub.add_parser("content-worker-once")
    content_worker.add_argument("--channel", default="us-economy")
    content_worker.add_argument("--type", required=True, choices=["MAIN_NEWS", "SINGLE_SHORT", "TOP5_SHORT"])
    content_worker.add_argument("--worker", required=True)
    content_worker.add_argument("--input-root", required=True, type=Path)
    publication = sub.add_parser("publication-enqueue")
    publication.add_argument("--plan-id", required=True)
    publication.add_argument("--review-note", required=True)
    publication_worker = sub.add_parser("publication-worker-once")
    publication_worker.add_argument("--channel", default="us-economy")
    publication_worker.add_argument("--worker", required=True)
    sub.add_parser("status")
    args = parser.parse_args()
    if args.command == "research":
        channel = load_channels(settings.channels_file)[args.channel]
        package = run_research(channel, date.fromisoformat(args.date), settings.artifacts_dir)
        errors = validate_research(package, min_sources=2)
        print(f"Collected {len(package.items)} items; gate={'PASS' if not errors else 'BLOCK'}")
        for error in errors:
            print(f"- {error}")
    elif args.command == "youtube-collect-stats":
        from sqlalchemy import create_engine
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from .video_statistics import collect_video_statistics
        channel = load_channels(settings.channels_file).get(args.channel)
        if not channel or not channel.enabled or not settings.database_url.startswith("postgresql"):
            raise ValueError("Enabled channel and PostgreSQL required")
        credentials = Credentials.from_authorized_user_file(str(settings.youtube_token_file))
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        if not credentials.valid:
            raise ValueError("An existing valid YouTube token is required")
        engine = create_engine(settings.database_url, pool_pre_ping=True)
        try:
            print(json.dumps(collect_video_statistics(engine, credentials, channel=args.channel,
                expected_channel_id=settings.youtube_channel_id, video_id=args.video_id), indent=2))
        finally:
            engine.dispose()
    elif args.command == "youtube-caption-upload":
        from .youtube import authorize_captions, upload_caption_track
        credentials = authorize_captions(settings.youtube_client_secrets_file, settings.youtube_caption_token_file,
                                          settings.youtube_channel_id, existing_upload_token=settings.youtube_token_file)
        caption_id = upload_caption_track(args.video_id, args.srt, credentials, settings.youtube_channel_id,
                                          name=args.name, timing_reviewed=args.timing_reviewed)
        print(f"Caption track uploaded: {caption_id}")
        if settings.database_url.startswith("postgresql"):
            from sqlalchemy import create_engine
            from .caption_store import record_caption
            engine = create_engine(settings.database_url, pool_pre_ping=True)
            try:
                record_caption(engine, caption_id=caption_id, video_id=args.video_id, srt=args.srt,
                               language="en", track_name=args.name, timing_method="reviewed", status="submitted")
                print("Caption upload recorded in PostgreSQL.")
            except Exception as exc:
                print(f"Caption exists on YouTube but DB recording failed ({type(exc).__name__}); do not upload again.")
                raise
            finally:
                engine.dispose()
    elif args.command == "youtube-caption-auth":
        from .youtube import authorize_captions
        authorize_captions(settings.youtube_client_secrets_file, settings.youtube_caption_token_file,
                           settings.youtube_channel_id, existing_upload_token=settings.youtube_token_file)
        print("Caption OAuth consent granted and configured channel verified.")
    elif args.command == "youtube-auth":
        from .youtube import authorize, verify_channel
        credentials = authorize(settings.youtube_client_secrets_file, settings.youtube_token_file)
        verify_channel(credentials, settings.youtube_channel_id)
        print("Authenticated YouTube channel matches configured ID.")
    elif args.command == "trend-groups":
        from sqlalchemy import create_engine
        from .trend_grouping import save_latest_groups
        channel = load_channels(settings.channels_file).get(args.channel)
        if not channel or not channel.enabled or not settings.database_url.startswith("postgresql"):
            raise ValueError("Enabled channel and PostgreSQL required")
        engine = create_engine(settings.database_url, pool_pre_ping=True)
        try:
            collection, groups = save_latest_groups(engine, args.channel)
            print(json.dumps({"collection_id": collection, "groups": groups,
                              "note": "Shared links suggest related topics; event identity remains unverified."}, ensure_ascii=False, indent=2))
        finally:
            engine.dispose()
    elif args.command in {"publication-enqueue", "publication-worker-once"}:
        from sqlalchemy import create_engine
        from .publication_queue import PublicationQueue
        if not settings.database_url.startswith("postgresql"):
            raise ValueError("PostgreSQL is required")
        engine = create_engine(settings.database_url, pool_pre_ping=True)
        try:
            if args.command == "publication-enqueue":
                print("Private publication job:", PublicationQueue(engine).enqueue(args.plan_id, review_note=args.review_note))
            else:
                from google.oauth2.credentials import Credentials
                from google.auth.transport.requests import Request
                from .publication_worker import run_once
                channel = load_channels(settings.channels_file).get(args.channel)
                if channel is None or not channel.enabled or not settings.youtube_token_file.is_file():
                    raise ValueError("Enabled channel and an existing OAuth token are required")
                credentials = Credentials.from_authorized_user_file(str(settings.youtube_token_file))
                if credentials.expired and credentials.refresh_token:
                    credentials.refresh(Request())
                video_id = run_once(engine, args.channel, args.worker, credentials, settings.youtube_channel_id,
                                    ffmpeg=settings.ffmpeg_bin)
                print(f"Private upload verified: {video_id}" if video_id else "No private publication job")
        finally:
            engine.dispose()
    elif args.command in {"content-plan", "content-worker-once"}:
        from sqlalchemy import create_engine
        channel = load_channels(settings.channels_file).get(args.channel)
        if channel is None or not channel.enabled or not settings.database_url.startswith("postgresql"):
            raise ValueError("An enabled channel and PostgreSQL are required")
        engine = create_engine(settings.database_url, pool_pre_ping=True)
        try:
            if args.command == "content-plan":
                from .content_plans import create_plan
                from .content_types import ContentType, fallback_format
                payload = json.loads(args.input.read_text(encoding="utf-8"))
                converted = False
                if payload["content_type"] == ContentType.TOP5_SHORT:
                    effective = fallback_format(payload["topics"])
                    if effective == ContentType.SINGLE_SHORT:
                        payload["content_type"] = effective.value
                        payload.pop("script", None)
                        payload.pop("assets", None)
                        payload.pop("ranking_basis", None)
                        payload.pop("period", None)
                        converted = True
                plan_id = create_plan(engine, args.channel, payload["content_type"], args.collection_id,
                                      payload["topics"], period=payload.get("period"),
                                      ranking_basis=payload.get("ranking_basis"),
                                      fallback_reason="Only one eligible event; create an independent single short." if converted else None)
                print(f"Created content plan: {plan_id}")
                if converted:
                    prepared = settings.artifacts_dir / args.channel / "prepared" / f"{plan_id}.json"
                    prepared.parent.mkdir(parents=True, exist_ok=True)
                    prepared.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                    print(f"Converted to SINGLE_SHORT; create its independent script and assets in: {prepared}")
            else:
                from .content_worker import run_once
                plan_id = run_once(engine, args.channel, channel.country, args.type, args.worker,
                                   args.input_root, settings.artifacts_dir / args.channel / "content",
                                   ffmpeg=settings.ffmpeg_bin)
                print(f"Ready for editorial review: {plan_id}" if plan_id else "No planned content")
        finally:
            engine.dispose()
    elif args.command == "content-script":
        from .content_script import content_script_prompt, validate_content_inputs, validate_content_script
        from .script import run_codex
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        errors = validate_content_inputs(payload["content_type"], payload["topics"], payload["research"],
                                         period=payload.get("period"), ranking_basis=payload.get("ranking_basis"))
        if errors:
            raise ValueError("Input gate: " + "; ".join(errors))
        raw = run_codex(content_script_prompt(payload["content_type"], payload["topics"], payload["research"],
                                             period=payload.get("period"), ranking_basis=payload.get("ranking_basis")),
                        args.output, command=settings.codex_command, timeout=settings.codex_timeout_seconds)
        errors = validate_content_script(payload["content_type"], payload["topics"], payload["research"], raw,
                                         period=payload.get("period"), ranking_basis=payload.get("ranking_basis"))
        report = args.output.with_suffix(".validation.json")
        report.write_text(json.dumps({"passed": not errors, "errors": errors,
            "note": "Structural checks do not establish truth, rights or rank evidence."}, indent=2), encoding="utf-8")
        print(f"Script gate: {'BLOCK' if errors else 'PASS'}; report: {report}")
        if errors:
            raise SystemExit(1)
    elif args.command == "content-render":
        from .content_production import render_content
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        result = render_content(payload["content_type"], payload["topics"], payload["research"],
            json.loads(args.script.read_text(encoding="utf-8")), json.loads(args.assets.read_text(encoding="utf-8")),
            args.output_dir, ffmpeg=settings.ffmpeg_bin, period=payload.get("period"),
            ranking_basis=payload.get("ranking_basis"),
            thumbnail_asset=json.loads(args.thumbnail_asset.read_text(encoding="utf-8")) if args.thumbnail_asset else None,
            audio_profile=args.audio_profile)
        print(json.dumps(result, indent=2))
    elif args.command == "event-render":
        from .event_production import render_event
        result = render_event(json.loads(args.research.read_text(encoding="utf-8")),
                              json.loads(args.script.read_text(encoding="utf-8")),
                              json.loads(args.assets.read_text(encoding="utf-8")),
                              args.output_dir, ffmpeg=settings.ffmpeg_bin)
        print(json.dumps(result, indent=2))
    elif args.command == "event-script":
        from .event_script import event_script_prompt, validate_event_research, validate_event_script
        from .script import run_codex
        research = json.loads(args.research.read_text(encoding="utf-8"))
        errors = validate_event_research(research)
        if errors:
            raise ValueError("Research gate: " + "; ".join(errors))
        raw = run_codex(event_script_prompt(research), args.output,
                        command=settings.codex_command, timeout=settings.codex_timeout_seconds)
        errors = validate_event_script(raw, research)
        report = args.output.with_suffix(".validation.json")
        report.write_text(json.dumps({"passed": not errors, "errors": errors,
            "note": "Structural checks only; independent factual, editorial and rights review required."}, indent=2), encoding="utf-8")
        print(f"Script gate: {'BLOCK' if errors else 'PASS'}; report: {report}")
        if errors:
            raise SystemExit(1)
    elif args.command in {"enqueue-reviewed-trend", "trend-worker-once"}:
        from sqlalchemy import create_engine
        from .production_queue import ProductionQueue
        channel = load_channels(settings.channels_file).get(args.channel)
        if channel is None or not channel.enabled:
            raise ValueError("Channel must exist and be enabled")
        if not settings.database_url.startswith("postgresql"):
            raise RuntimeError("Production queue requires PostgreSQL")
        engine = create_engine(settings.database_url, pool_pre_ping=True)
        try:
            if args.command == "enqueue-reviewed-trend":
                job_id = ProductionQueue(engine).enqueue_reviewed_trend(
                    args.channel, args.keyword, args.event_key, args.reason)
                print(f"Queued reviewed event: {job_id}")
            else:
                from .trend_worker import run_once
                job_id = run_once(engine, args.channel, channel.country, args.worker, settings.artifacts_dir)
                print(f"Rechecked and blocked for research: {job_id}" if job_id else "No pending job")
        finally:
            engine.dispose()
    elif args.command == "trends":
        from sqlalchemy import create_engine
        from .trends import collect
        if not settings.database_url.startswith("postgresql"):
            raise RuntimeError("Trends collection requires a migrated PostgreSQL database")
        channel = load_channels(settings.channels_file).get(args.channel)
        if channel is None or not channel.enabled or channel.country != args.region:
            raise ValueError("Channel must be enabled and match the requested region")
        items = collect(create_engine(settings.database_url, pool_pre_ping=True), args.channel, args.region)
        for item in items:
            print(f"{item.volume_raw or '?':>10}  {item.keyword}")
        print(f"Collected {len(items)} trends; RSS period and active status are unspecified.")
    else:
        store = JobStore(Path("data/woori_youtube.db"))
        for row in store.list_jobs():
            print(row)


if __name__ == "__main__":
    main()
