from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    RETRY = "retry"
    BLOCKED = "blocked"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass
class NewsItem:
    title: str
    url: str
    source: str
    published_at: str | None = None
    summary: str = ""
    category: str = "economy"
    content_hash: str = ""


@dataclass
class ResearchPackage:
    channel_id: str
    date: str
    items: list[NewsItem]
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    validation_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"channel_id": self.channel_id, "date": self.date, "created_at": self.created_at,
                "items": [asdict(item) for item in self.items], "validation_errors": self.validation_errors}


@dataclass
class VideoScript:
    channel_id: str
    date: str
    title: str
    description: str
    language: str
    scenes: list[dict[str, Any]]
    claims: list[dict[str, Any]]
    version: int = 1
    script_id: str = field(default_factory=lambda: str(uuid4()))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
