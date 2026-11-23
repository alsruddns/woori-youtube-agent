"""Group related keywords by explicit shared links; groups are not verified events."""
import hashlib
import json
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import text


def canonical_url(url: str) -> str | None:
    try:
        parts = urlsplit(url)
        host = parts.hostname
    except ValueError:
        return None
    if parts.scheme.lower() != "https" or not host or parts.username or parts.password:
        return None
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
             if not key.lower().startswith("utm_") and key.lower() not in {"fbclid", "gclid"}]
    return urlunsplit(("https", parts.netloc.lower(), parts.path.rstrip("/") or "/", urlencode(sorted(query)), ""))


def candidate_groups(observations: list[dict]) -> list[dict]:
    entries = {}
    for item in observations:
        keyword = str(item.get("keyword", "")).strip()
        if not keyword:
            continue
        source_urls = item.get("news_urls")
        urls = {canonical_url(url) for url in source_urls if isinstance(url, str)} if isinstance(source_urls, list) else set()
        entries.setdefault(keyword, set()).update(url for url in urls if url)
    keywords = sorted(entries)
    parent = {word: word for word in keywords}
    def find(word):
        while parent[word] != word:
            parent[word] = parent[parent[word]]
            word = parent[word]
        return word
    owners = {}
    for word in keywords:
        for url in entries[word]:
            if url in owners:
                parent[find(word)] = find(owners[url])
            else:
                owners[url] = word
    groups = {}
    for word in keywords:
        groups.setdefault(find(word), []).append(word)
    result = []
    for words in groups.values():
        if len(words) < 2:
            continue
        counts = {}
        for word in words:
            for url in entries[word]:
                counts[url] = counts.get(url, 0) + 1
        result.append({"keywords": sorted(words), "shared_urls": sorted(url for url, count in counts.items() if count >= 2),
                       "review_status": "unreviewed"})
    return sorted(result, key=lambda group: group["keywords"])


def save_latest_groups(engine, channel_id: str) -> tuple[int, list[dict]]:
    with engine.begin() as conn:
        latest = conn.execute(text("""SELECT id,success,collected_at >= now()-interval '30 minutes' AS fresh
            FROM trend_collections WHERE channel_id=:channel ORDER BY collected_at DESC,id DESC LIMIT 1"""),
            {"channel": channel_id}).mappings().first()
        if not latest or not latest["success"] or not latest["fresh"]:
            raise ValueError("The latest trend collection is missing, failed, or stale")
        rows = conn.execute(text("SELECT keyword,news_urls FROM trend_observations WHERE collection_id=:id"),
                            {"id": latest["id"]}).mappings()
        groups = candidate_groups([dict(row) for row in rows])
        for group in groups:
            fingerprint = hashlib.sha256(json.dumps(group["keywords"], ensure_ascii=False).encode()).hexdigest()
            conn.execute(text("""INSERT INTO trend_group_candidates(collection_id,fingerprint,keywords,shared_urls)
                VALUES (:id,:fingerprint,CAST(:keywords AS JSON),CAST(:urls AS JSON))
                ON CONFLICT(collection_id,fingerprint) DO NOTHING"""),
                {"id": latest["id"], "fingerprint": fingerprint,
                 "keywords": json.dumps(group["keywords"], ensure_ascii=False),
                 "urls": json.dumps(group["shared_urls"], ensure_ascii=False)})
        return latest["id"], groups
