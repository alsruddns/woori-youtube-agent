"""Google's public Trending Now RSS. No period or status is inferred from this feed."""
from __future__ import annotations

import re
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

NS = {"ht": "https://trends.google.com/trending/rss"}

@dataclass(frozen=True)
class Trend:
    keyword: str
    volume_raw: str | None
    volume_lower_bound: int | None
    news_urls: list[str]
    published_at: str | None


def normalize_volume(value: str) -> int | None:
    match = re.fullmatch(r"\s*([\d,.]+)\s*([KMB]?)\+?\s*", value, re.I)
    if not match:
        return None
    try:
        return int(float(match.group(1).replace(",", "")) * {"": 1, "K": 1000, "M": 1000000, "B": 1000000000}[match.group(2).upper()])
    except ValueError:
        return None


def parse_trends(payload: bytes) -> list[Trend]:
    root = ET.fromstring(payload)
    if root.tag != "rss" or root.find("channel") is None:
        raise ValueError("Unexpected Trends RSS document")
    result = []
    for item in root.findall("./channel/item"):
        keyword = (item.findtext("title") or "").strip()
        if not keyword:
            continue
        volume = (item.findtext("ht:approx_traffic", namespaces=NS) or "").strip()
        urls = [(x.text or "").strip() for x in item.findall("ht:news_item/ht:news_item_url", NS)]
        result.append(Trend(keyword, volume or None, normalize_volume(volume),
                            [u for u in urls if u.startswith("https://")], item.findtext("pubDate")))
    return sorted(result, key=lambda t: -(t.volume_lower_bound if t.volume_lower_bound is not None else -1))[:100]


def fetch_trends(region: str = "US") -> list[Trend]:
    if not re.fullmatch(r"[A-Z]{2}", region):
        raise ValueError("region must be a two-letter country code")
    request = urllib.request.Request(f"https://trends.google.com/trending/rss?geo={region}", headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = response.read(4_000_001)
    if len(payload) > 4_000_000:
        raise ValueError("Trends feed exceeds size limit")
    return parse_trends(payload)


def collect(engine, channel: str, region: str) -> list[Trend]:
    from sqlalchemy import text
    observed = datetime.now(timezone.utc)
    try:
        trends = fetch_trends(region)
        if not trends:
            raise ValueError("Trends feed returned no items")
    except Exception as exc:
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO trend_collections(channel_id, region, collected_at, success, error) VALUES (:channel,:region,:at,false,:error)"),
                         {"channel": channel, "region": region, "at": observed, "error": f"{type(exc).__name__}: {exc}"[:1000]})
        raise
    import json
    with engine.begin() as conn:
        collection_id = conn.execute(text("INSERT INTO trend_collections(channel_id,region,collected_at,success) VALUES (:channel,:region,:at,true) RETURNING id"),
            {"channel": channel, "region": region, "at": observed}).scalar_one()
        for trend in trends:
            conn.execute(text("INSERT INTO trend_observations(collection_id,keyword,volume_raw,volume_lower_bound,news_urls,published_at) VALUES (:id,:keyword,:volume_raw,:volume_lower_bound,CAST(:news_urls AS JSON),:published_at)"),
                {"id": collection_id, **{**asdict(trend), "news_urls": json.dumps(trend.news_urls)}})
    return trends
