from __future__ import annotations

import hashlib
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from .models import NewsItem, ResearchPackage


def _text(node: ET.Element, names: tuple[str, ...]) -> str:
    for name in names:
        element = node.find(name)
        if element is not None and element.text:
            return element.text.strip()
    return ""


def parse_rss(xml: str, source: str, category: str) -> list[NewsItem]:
    root = ET.fromstring(xml)
    entries: list[NewsItem] = []
    for item in root.findall(".//item"):
        title = _text(item, ("title",))
        link = _text(item, ("link",))
        summary = _text(item, ("description",))
        published = _text(item, ("pubDate",)) or None
        if title and link:
            normalized = " ".join(title.split()).casefold() + "|" + link.rstrip("/").casefold()
            entries.append(NewsItem(title, link, source, published, summary, category,
                                    hashlib.sha256(normalized.encode()).hexdigest()))
    # Atom support
    ns = {"a": "http://www.w3.org/2005/Atom"}
    for item in root.findall("a:entry", ns):
        title = _text(item, ("a:title",))
        link_node = item.find("a:link", ns)
        link = link_node.attrib.get("href", "") if link_node is not None else ""
        summary = _text(item, ("a:summary", "a:content"))
        published = _text(item, ("a:published", "a:updated")) or None
        if title and link:
            normalized = " ".join(title.split()).casefold() + "|" + link.rstrip("/").casefold()
            entries.append(NewsItem(title, link, source, published, summary, category,
                                    hashlib.sha256(normalized.encode()).hexdigest()))
    return entries


def fetch_feed(url: str, category: str = "economy", timeout: int = 15) -> list[NewsItem]:
    request = urllib.request.Request(url, headers={"User-Agent": "WooriYouTubeAgent/0.1 (+local news research)"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read(4_000_000)
    return parse_rss(payload.decode("utf-8", errors="replace"), url, category)


def build_research_package(channel_id: str, date: str, feeds: list[tuple[str, str]], fetcher=fetch_feed) -> ResearchPackage:
    unique: dict[str, NewsItem] = {}
    errors: list[str] = []
    for url, category in feeds:
        try:
            for item in fetcher(url, category):
                unique.setdefault(item.content_hash, item)
        except Exception as exc:  # preserve source-level failures in the package
            errors.append(f"{url}: {type(exc).__name__}: {exc}")
    items = list(unique.values())
    return ResearchPackage(channel_id, date, items, validation_errors=errors)


def validate_research(package: ResearchPackage, *, min_sources: int = 2, require_recent: bool = False) -> list[str]:
    errors = list(package.validation_errors)
    if len(package.items) < min_sources:
        errors.append(f"At least {min_sources} distinct items are required.")
    sources = {item.source for item in package.items}
    if len(sources) < min_sources:
        errors.append(f"At least {min_sources} distinct source feeds are required.")
    for item in package.items:
        if not item.title.strip() or not item.url.startswith("https://"):
            errors.append(f"Invalid title or non-HTTPS source URL: {item.url}")
        if require_recent and not item.published_at:
            errors.append(f"Missing publication date: {item.url}")
        if require_recent and item.published_at:
            try:
                published = parsedate_to_datetime(item.published_at)
                if published.tzinfo is None:
                    published = published.replace(tzinfo=timezone.utc)
                if (datetime.now(timezone.utc) - published).days > 3:
                    errors.append(f"Stale source item: {item.url}")
            except (TypeError, ValueError, OverflowError):
                errors.append(f"Unparseable publication date: {item.url}")
    return errors
