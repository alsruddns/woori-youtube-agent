from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Channel:
    channel_id: str
    locale: str
    language_name: str
    country: str
    timezone: str
    categories: tuple[str, ...]
    enabled: bool
    target_minutes: int
    rss_feeds: tuple[tuple[str, str], ...]
    tts_engine: str
    tts_language_code: str
    tts_voice: str
    disclaimer: str


def load_channels(path: Path) -> dict[str, Channel]:
    """Read the simple YAML channel catalog. PyYAML is optional; JSON-compatible YAML fallback."""
    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("Install PyYAML to load channels.yaml (pip install pyyaml).") from exc
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    channels = raw.get("channels", {})
    return {key: Channel(key, value["locale"], value["language_name"], value["country"],
                         value["timezone"], tuple(value.get("categories", ())),
                         bool(value.get("enabled", False)), int(value.get("target_minutes", 15)),
                         tuple((feed, "economy") if isinstance(feed, str) else
                               (feed["url"], feed.get("category", "economy"))
                               for feed in value.get("rss_feeds", ())),
                         value.get("tts", {}).get("engine", "kokoro"),
                         value.get("tts", {}).get("language_code", "a"),
                         value.get("tts", {}).get("voice", "af_heart"),
                         value.get("disclaimer", "This is news commentary, not investment advice.")) for key, value in channels.items()}
