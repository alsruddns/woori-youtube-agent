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
    ContentType.TOP5_SHORT: ContentSpec(2, 40, 60, 90, 1080, 1920, 2, 5),
}


def fallback_format(topics: list[dict]) -> ContentType:
    """Route one verified event to a single short; no event is a deferred task."""
    if not topics:
        raise ValueError("No eligible events; defer the task")
    if len(topics) == 1:
        validate_topics(ContentType.SINGLE_SHORT, topics)
        return ContentType.SINGLE_SHORT
    validate_topics(ContentType.TOP5_SHORT, topics)
    return ContentType.TOP5_SHORT


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
    if len(topics) != 5:
        raise ValueError("A ranked countdown requires five distinct events")
    if period != "past_24_hours" or ranking_basis != "official_distinct":
        raise ValueError("Top 5 requires verified distinct official ranks from the past 24 hours")
    ranks = [item.get("rank") for item in topics]
    if any(type(rank) is not int for rank in ranks) or set(ranks) != {1, 2, 3, 4, 5}:
        raise ValueError("Official ranks must be uniquely established from 1 to 5")
    if any(not item.get("keyword") or not item.get("rank_evidence_url", "").startswith("https://") for item in topics):
        raise ValueError("Every rank needs a keyword and evidence URL")
    return sorted(topics, key=lambda item: item["rank"], reverse=True)


def compilation_selection(topics: list[dict], *, period: str | None = None,
                          ranking_basis: str | None = None) -> dict:
    """Select an honest presentation mode; signals do not prove editorial facts."""
    validate_topics(ContentType.TOP5_SHORT, topics)
    if any(not isinstance(item.get("keyword"), str) or not item["keyword"].strip() for item in topics):
        raise ValueError("Every event needs a keyword")
    if ranking_basis == "official_distinct":
        try:
            ordered = verified_top5(topics, period=period, ranking_basis=ranking_basis)
            return {"mode": "VERIFIED_RANKING", "period": period, "basis": ranking_basis, "items": ordered}
        except ValueError as exc:
            fallback = compilation_selection(topics)
            fallback.update({"requested_basis": ranking_basis, "fallback_reason": str(exc)})
            return fallback
    if period not in {None, "unspecified"}:
        raise ValueError("RSS fallback cannot establish a 4-hour or 24-hour period")
    if ranking_basis == "volume_bucket_ordered":
        volumes = [item.get("volume_lower_bound") for item in topics]
        if any(type(value) is not int or value < 0 for value in volumes):
            raise ValueError("Each event needs a known nonnegative volume bucket")
        ordered = sorted(topics, key=lambda item: -item["volume_lower_bound"])
        ties = sorted({value for value in volumes if volumes.count(value) > 1}, reverse=True)
        return {"mode": "VOLUME_BUCKET_ORDERED", "period": "unspecified", "basis": ranking_basis,
                "disclosure": "Volume buckets can tie; not an official ranking.", "tie_buckets": ties,
                "items": [{k: v for k, v in item.items() if k != "rank"} for item in ordered]}
    if ranking_basis == "editorial_countdown":
        if (len(topics) != 5 or {item.get("rank") for item in topics} != {1, 2, 3, 4, 5}
                or any(type(item.get("rank")) is not int or not str(item.get("selection_reason", "")).strip() for item in topics)):
            fallback = compilation_selection(topics)
            fallback.update({"requested_basis": ranking_basis, "fallback_reason": "Editorial order lacks five distinct explained selections."})
            return fallback
        ordered = sorted(topics, key=lambda item: item["rank"], reverse=True)
        return {"mode": "EDITORIAL_COUNTDOWN", "period": period or "unspecified", "basis": ranking_basis,
                "disclosure": "Now Trends editorial selection; not an official Google ranking.", "items": ordered}
    if ranking_basis not in {None, "unranked_highlights"}:
        raise ValueError("Unsupported ranking basis")
    return {"mode": "UNRANKED_HIGHLIGHTS", "period": period or "unspecified",
            "basis": "unranked_highlights", "disclosure": "Selected stories, not an official ranking.",
            "items": [{k: v for k, v in item.items() if k != "rank"} for item in topics]}
