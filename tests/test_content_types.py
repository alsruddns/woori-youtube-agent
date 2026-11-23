import pytest
from woori_youtube.content_types import ContentType, SPECS, validate_topics, verified_top5


def topics():
    return [{"event_key": f"event-{i}", "keyword": f"topic-{i}", "rank": i,
             "rank_evidence_url": "https://trends.google.com/"} for i in range(1, 6)]


def test_independent_specs_and_cross_format_topic_counts():
    assert [SPECS[t].daily_goal for t in ContentType] == [2, 10, 2]
    validate_topics(ContentType.MAIN_NEWS, topics())
    validate_topics(ContentType.SINGLE_SHORT, topics()[:1])
    with pytest.raises(ValueError):
        validate_topics(ContentType.MAIN_NEWS, topics()[:3])
    duplicate = topics()
    duplicate[1]["event_key"] = duplicate[0]["event_key"]
    with pytest.raises(ValueError, match="distinct"):
        validate_topics(ContentType.MAIN_NEWS, duplicate)


def test_top5_requires_distinct_verified_ranks_and_countdown():
    assert [x["rank"] for x in verified_top5(topics(), period="past_24_hours", ranking_basis="official_distinct")] == [5, 4, 3, 2, 1]
    with pytest.raises(ValueError, match="verified"):
        verified_top5(topics(), period="unknown", ranking_basis="rss")
    tied = topics()
    tied[-1]["rank"] = 4
    with pytest.raises(ValueError, match="uniquely"):
        verified_top5(tied, period="past_24_hours", ranking_basis="official_distinct")


def test_countdown_script_must_match_each_rank_to_its_event():
    from woori_youtube.content_script import validate_content_script
    selected = topics()
    research = {}
    for topic in selected:
        research[topic["event_key"]] = {"event": topic["keyword"], "sensitivity": "ordinary",
            "uncertainties": ["Conditions may change."],
            "sources": [{"id": f"s{i}", "url": f"https://source{i}.example/a", "publisher": "Source",
                         "retrieved_at": "2026-11-23T00:00:00Z", "text": "A reported fact."} for i in range(2)],
            "claims": [{"id": "claim", "text": "A reported fact.",
                        "evidence": [{"source_id": "s0", "excerpt": "A reported fact."}]}]}
    script = {"title": "Trends", "description": "https://source0.example/a", "language": "en-US", "scenes": [
        {"rank": item["rank"], "event_keys": [item["event_key"]], "visual": "Chart",
         "narration": "This event is in the news and the source describes a reported fact.",
         "claim_refs": [{"event_key": item["event_key"], "claim_id": "claim"}]}
        for item in reversed(selected)]}
    assert validate_content_script(ContentType.TOP5_SHORT, selected, research, script,
                                   period="past_24_hours", ranking_basis="official_distinct") == []
    script["scenes"][0]["rank"] = 4
    assert any("Countdown" in x for x in validate_content_script(
        ContentType.TOP5_SHORT, selected, research, script,
        period="past_24_hours", ranking_basis="official_distinct"))
