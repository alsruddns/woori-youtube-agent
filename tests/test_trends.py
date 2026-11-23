from woori_youtube.trends import normalize_volume, parse_trends


def test_volume_is_bucket_lower_bound():
    assert normalize_volume("1.2M+") == 1200000
    assert normalize_volume("100,000+") == 100000
    assert normalize_volume("unknown") is None


def test_feed_ranks_buckets_and_preserves_missing_fields():
    xml = b'''<rss xmlns:ht="https://trends.google.com/trending/rss"><channel>
      <item><title>Small</title><ht:approx_traffic>10K+</ht:approx_traffic></item>
      <item><title>Big</title><ht:approx_traffic>1M+</ht:approx_traffic><ht:news_item><ht:news_item_url>https://example.com/a</ht:news_item_url></ht:news_item></item>
      <item><title>Unknown</title></item></channel></rss>'''
    items = parse_trends(xml)
    assert [x.keyword for x in items] == ["Big", "Small", "Unknown"]
    assert items[0].news_urls == ["https://example.com/a"]
    assert items[2].volume_lower_bound is None
