import pytest
from woori_youtube.content_types import ContentType, SPECS, validate_topics, verified_top5, compilation_selection, fallback_format


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


def test_insufficient_ranking_falls_back_to_unranked_without_invented_ordinals():
    selection = compilation_selection(topics()[:3])
    assert selection["mode"] == "UNRANKED_HIGHLIGHTS"
    assert all("rank" not in item for item in selection["items"])
    assert selection["period"] == "unspecified"
    with pytest.raises(ValueError, match="2–5"):
        compilation_selection(topics()[:1])
    assert fallback_format(topics()[:1]) == ContentType.SINGLE_SHORT
    with pytest.raises(ValueError, match="No eligible"):
        fallback_format([])


def test_editorial_countdown_requires_documented_selection_reasons():
    selected = topics()
    fallback = compilation_selection(selected, ranking_basis="editorial_countdown")
    assert fallback["mode"] == "UNRANKED_HIGHLIGHTS" and fallback["fallback_reason"]
    for item in selected:
        item["selection_reason"] = "Reviewed for relevance and supporting reporting"
    selection = compilation_selection(selected, ranking_basis="editorial_countdown")
    assert selection["mode"] == "EDITORIAL_COUNTDOWN"
    assert [item["rank"] for item in selection["items"]] == [5, 4, 3, 2, 1]
    assert "not an official" in selection["disclosure"]


def test_volume_buckets_record_ties_without_exact_ranking():
    selected = topics()[:3]
    for topic, value in zip(selected, [1000, 5000, 5000]):
        topic["volume_lower_bound"] = value
    selection = compilation_selection(selected, ranking_basis="volume_bucket_ordered")
    assert [item["volume_lower_bound"] for item in selection["items"]] == [5000, 5000, 1000]
    assert selection["tie_buckets"] == [5000]
    assert all("rank" not in item for item in selection["items"])
    with pytest.raises(ValueError, match="cannot establish"):
        compilation_selection(selected, period="past_24_hours", ranking_basis="volume_bucket_ordered")


def test_unranked_script_requires_disclosure_and_rejects_rank_graphics():
    from woori_youtube.content_script import validate_content_script
    selected = topics()[:2]
    research = {topic["event_key"]: {"event": topic["keyword"], "sensitivity": "ordinary",
        "uncertainties": ["Conditions may change."],
        "sources": [{"id": f"s{i}", "url": f"https://source{i}.example/a", "publisher": "Source",
            "retrieved_at": "2026-11-23T00:00:00Z", "text": "A reported fact."} for i in range(2)],
        "claims": [{"id": "claim", "text": "A reported fact.",
            "evidence": [{"source_id": "s0", "excerpt": "A reported fact."}]}]} for topic in selected}
    script = {"title": "Two trending stories", "description": "Selected stories, not an official ranking. https://source0.example/a",
        "language": "en-US", "scenes": [{"event_keys": [item["event_key"]], "visual": "Chart",
            "narration": "The source reports a fact today and this scene explains the context in a careful way for viewers who want to understand this story and its continuing developments.",
            "claim_refs": [{"event_key": item["event_key"], "claim_id": "claim"}]} for item in selected]}
    assert validate_content_script(ContentType.TOP5_SHORT, selected, research, script) == []
    script["scenes"][0]["rank"] = 2
    assert any("Unranked" in error for error in validate_content_script(ContentType.TOP5_SHORT, selected, research, script))
