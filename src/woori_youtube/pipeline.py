from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from .channels import Channel
from .ingest import build_research_package, validate_research
from .models import ResearchPackage
from .script import run_codex, script_prompt, validate_script


class PipelineBlocked(RuntimeError):
    pass


def run_research(channel: Channel, run_date: date, output_dir: Path, fetcher=None) -> ResearchPackage:
    feeds = list(channel.rss_feeds)
    kwargs: dict[str, Any] = {}
    if fetcher is not None:
        kwargs["fetcher"] = fetcher
    package = build_research_package(channel.channel_id, run_date.isoformat(), feeds, **kwargs)
    target = output_dir / channel.channel_id / run_date.isoformat() / "research.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(package.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return package


def run_script(channel: Channel, package: ResearchPackage, output_dir: Path, *, command: str = "codex", timeout: int = 1800) -> dict[str, Any]:
    errors = validate_research(package, min_sources=2)
    if errors:
        raise PipelineBlocked("Research validation failed: " + "; ".join(errors))
    path = output_dir / channel.channel_id / package.date / "script.json"
    raw = run_codex(script_prompt(package, channel.locale, channel.language_name, channel.target_minutes, channel.disclaimer), path,
                    command=command, timeout=timeout)
    errors = validate_script(raw, package, target_minutes=channel.target_minutes,
                             require_categories={item.category for item in package.items if item.category in channel.categories},
                             disclaimer=channel.disclaimer)
    (path.parent / "script.validation.json").write_text(json.dumps({"passed": not errors, "errors": errors}, indent=2), encoding="utf-8")
    if errors:
        raise PipelineBlocked("Script validation failed: " + "; ".join(errors))
    return raw
