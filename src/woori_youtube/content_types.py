"""Independent production specifications and conservative ranking rules."""
from dataclasses import dataclass
from enum import StrEnum


class ContentType(StrEnum):
    MAIN_NEWS = "MAIN_NEWS"
    SINGLE_SHORT = "SINGLE_SHORT"
    TOP5_SHORT = "TOP5_SHORT"


@dataclass(frozen=True)
class ContentSpec:
    daily_goal: int
    min_seconds: int
    target_seconds: int
    max_seconds: int
    width: int
    height: int
    min_topics: int
    max_topics: int


SPECS = {
    ContentType.MAIN_NEWS: ContentSpec(2, 480, 720, 1080, 1920, 1080, 4, 10),
    ContentType.SINGLE_SHORT: ContentSpec(10, 20, 40, 60, 1080, 1920, 1, 1),
    ContentType.TOP5_SHORT: ContentSpec(2, 40, 60, 90, 1080, 1920, 5, 5),
}


def validate_topics(content_type: ContentType, topics: list[dict]) -> None:
    spec = SPECS[ContentType(content_type)]
    if not spec.min_topics <= len(topics) <= spec.max_topics:
        raise ValueError(f"{content_type} requires {spec.min_topics}–{spec.max_topics} distinct events")
    keys = [topic.get("event_key") for topic in topics]
    if any(not isinstance(key, str) or not key.strip() for key in keys) or len(set(keys)) != len(keys):
        raise ValueError("Each topic needs a distinct reviewed event key")


def verified_top5(topics: list[dict], *, period: str, ranking_basis: str) -> list[dict]:
    """Require externally verified distinct official ranks; never rank RSS buckets ourselves."""
    validate_topics(ContentType.TOP5_SHORT, topics)
    if period != "past_24_hours" or ranking_basis != "official_distinct":
        raise ValueError("Top 5 requires verified distinct official ranks from the past 24 hours")
    ranks = [item.get("rank") for item in topics]
    if any(type(rank) is not int for rank in ranks) or set(ranks) != {1, 2, 3, 4, 5}:
        raise ValueError("Official ranks must be uniquely established from 1 to 5")
    if any(not item.get("keyword") or not item.get("rank_evidence_url", "").startswith("https://") for item in topics):
        raise ValueError("Every rank needs a keyword and evidence URL")
    return sorted(topics, key=lambda item: item["rank"], reverse=True)
