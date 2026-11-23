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
    sub.add_parser("status")
    args = parser.parse_args()
    if args.command == "research":
        channel = load_channels(settings.channels_file)[args.channel]
        package = run_research(channel, date.fromisoformat(args.date), settings.artifacts_dir)
        errors = validate_research(package, min_sources=2)
        print(f"Collected {len(package.items)} items; gate={'PASS' if not errors else 'BLOCK'}")
        for error in errors:
            print(f"- {error}")
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
