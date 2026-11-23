from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from .channels import load_channels
from .config import settings
from .ingest import validate_research
from .pipeline import run_research
from .store import JobStore


def main() -> None:
    parser = argparse.ArgumentParser(prog="woori-youtube")
    sub = parser.add_subparsers(dest="command", required=True)
    research = sub.add_parser("research")
    research.add_argument("--channel", default="us-economy")
    research.add_argument("--date", default=date.today().isoformat())
    trends = sub.add_parser("trends")
    trends.add_argument("--channel", default="us-economy")
    trends.add_argument("--region", default="US")
    sub.add_parser("youtube-auth")
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
    content_plan = sub.add_parser("content-plan")
    content_plan.add_argument("--channel", default="us-economy")
    content_plan.add_argument("--collection-id", required=True, type=int)
    content_plan.add_argument("--input", required=True, type=Path)
    content_worker = sub.add_parser("content-worker-once")
    content_worker.add_argument("--channel", default="us-economy")
    content_worker.add_argument("--type", required=True, choices=["MAIN_NEWS", "SINGLE_SHORT", "TOP5_SHORT"])
    content_worker.add_argument("--worker", required=True)
    content_worker.add_argument("--input-root", required=True, type=Path)
    sub.add_parser("status")
    args = parser.parse_args()
    if args.command == "research":
        channel = load_channels(settings.channels_file)[args.channel]
        package = run_research(channel, date.fromisoformat(args.date), settings.artifacts_dir)
        errors = validate_research(package, min_sources=2)
        print(f"Collected {len(package.items)} items; gate={'PASS' if not errors else 'BLOCK'}")
        for error in errors:
            print(f"- {error}")
    elif args.command == "youtube-auth":
        from .youtube import authorize, verify_channel
        credentials = authorize(settings.youtube_client_secrets_file, settings.youtube_token_file)
        verify_channel(credentials, settings.youtube_channel_id)
        print("Authenticated YouTube channel matches configured ID.")
    elif args.command in {"content-plan", "content-worker-once"}:
        from sqlalchemy import create_engine
        channel = load_channels(settings.channels_file).get(args.channel)
        if channel is None or not channel.enabled or not settings.database_url.startswith("postgresql"):
            raise ValueError("An enabled channel and PostgreSQL are required")
        engine = create_engine(settings.database_url, pool_pre_ping=True)
        try:
            if args.command == "content-plan":
                from .content_plans import create_plan
                payload = json.loads(args.input.read_text(encoding="utf-8"))
                plan_id = create_plan(engine, args.channel, payload["content_type"], args.collection_id,
                                      payload["topics"], period=payload.get("period"),
                                      ranking_basis=payload.get("ranking_basis"))
                print(f"Created content plan: {plan_id}")
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
        raw = run_codex(content_script_prompt(payload["content_type"], payload["topics"], payload["research"]),
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
            ranking_basis=payload.get("ranking_basis"))
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
