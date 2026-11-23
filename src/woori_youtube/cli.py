from __future__ import annotations

import argparse
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
