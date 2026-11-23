from woori_youtube.ingest import parse_rss, validate_research
from woori_youtube.models import NewsItem, ResearchPackage


def test_parse_rss_and_stable_dedup_key():
    xml = """<rss><channel><item><title>Fed holds rates steady</title><link>https://example.gov/a</link>
    <description>Officials kept the range unchanged.</description><pubDate>Mon, 23 Nov 2026 12:00:00 GMT</pubDate></item></channel></rss>"""
    first = parse_rss(xml, "https://example.gov/feed", "economy")[0]
    second = parse_rss(xml, "https://example.gov/feed", "economy")[0]
    assert first.title == "Fed holds rates steady"
    assert first.content_hash == second.content_hash
    assert first.url.startswith("https://")


def test_research_requires_multiple_distinct_sources():
    package = ResearchPackage("us-economy", "2026-11-23", [
        NewsItem("A", "https://a.gov/1", "feed-a", summary="A", content_hash="a"),
        NewsItem("B", "https://a.gov/2", "feed-a", summary="B", content_hash="b"),
    ])
    assert any("distinct source feeds" in error for error in validate_research(package, min_sources=2))
