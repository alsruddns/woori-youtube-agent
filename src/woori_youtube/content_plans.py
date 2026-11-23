"""Store reviewed event selections without conflating video types."""
import hashlib
import json
from uuid import uuid4

from sqlalchemy import text
from .content_types import ContentType, validate_topics, verified_top5


def create_plan(engine, channel: str, content_type: ContentType, collection_id: int,
                topics: list[dict], *, ranking_basis: str | None = None,
                period: str | None = None, max_age_minutes: int = 30) -> str:
    content_type = ContentType(content_type)
    if not channel.strip() or max_age_minutes < 1:
        raise ValueError("Channel and positive freshness limit are required")
    validate_topics(content_type, topics)
    ranking = None
    if content_type == ContentType.TOP5_SHORT:
        ranking = verified_top5(topics, period=period, ranking_basis=ranking_basis)
        identity = [(item["rank"], item["event_key"]) for item in ranking]
    else:
        identity = sorted(item["event_key"] for item in topics)
    fingerprint = hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode("utf-8")).hexdigest()
    plan_id = str(uuid4())
    with engine.begin() as conn:
        latest = conn.execute(text("""SELECT id, success,
            collected_at >= now()-make_interval(mins => :age) AS fresh
            FROM trend_collections WHERE channel_id=:channel ORDER BY collected_at DESC,id DESC LIMIT 1"""),
            {"channel": channel, "age": max_age_minutes}).mappings().first()
        if not latest or latest["id"] != collection_id or not latest["success"] or not latest["fresh"]:
            raise ValueError("Plan requires the latest successful fresh collection")
        for topic in topics:
            keyword = topic.get("keyword")
            if not keyword or not conn.execute(text("""SELECT 1 FROM trend_observations
                WHERE collection_id=:collection AND keyword=:keyword LIMIT 1"""),
                {"collection": collection_id, "keyword": keyword}).scalar_one_or_none():
                raise ValueError("Every keyword must occur in the latest collection")
        inserted = conn.execute(text("""INSERT INTO content_plans
            (plan_id,channel_id,content_type,collection_id,fingerprint,topics,ranking_snapshot)
            VALUES (:id,:channel,:type,:collection,:fingerprint,CAST(:topics AS JSON),CAST(:ranking AS JSON))
            ON CONFLICT(channel_id,content_type,fingerprint) DO NOTHING RETURNING plan_id"""),
            {"id": plan_id, "channel": channel, "type": content_type.value, "collection": collection_id,
             "fingerprint": fingerprint, "topics": json.dumps(topics),
             "ranking": json.dumps({"period": period, "basis": ranking_basis, "items": ranking}) if ranking else None}).scalar_one_or_none()
        if not inserted:
            raise ValueError("Equivalent content for this channel and type already exists")
    return plan_id
