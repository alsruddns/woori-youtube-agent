from woori_youtube.event_script import validate_event_research, validate_event_script


def research():
    return {"event": "Coastal water levels", "sensitivity": "sensitive",
            "uncertainties": ["Forecasts may change."],
            "sources": [{"id": f"s{i}", "url": f"https://source{i}.example/report",
                         "publisher": f"Source {i}", "retrieved_at": "2026-11-23T00:00:00Z",
                         "text": "Water levels may rise."} for i in range(3)],
            "claims": [{"id": "c1", "text": "Water levels may rise.",
                        "evidence": [{"source_id": "s0", "excerpt": "Water levels may rise."}]}]}


def test_sensitive_research_requires_independent_domains_and_traceable_evidence():
    data = research()
    assert validate_event_research(data) == []
    data["sources"][2]["url"] = data["sources"][0]["url"]
    data["claims"][0]["evidence"][0]["excerpt"] = "invented"
    errors = validate_event_research(data)
    assert any("3 distinct" in error for error in errors)
    assert any("absent" in error for error in errors)


def test_script_does_not_accept_claimed_duration_as_length():
    script = {"title": "Title", "description": "Description", "language": "en-US",
              "scenes": [{"narration": "A short line.", "visual": "Diagram", "claim_ids": ["c1"], "duration_seconds": 900}]}
    assert any("3 words" in error for error in validate_event_script(script, research()))
    script["scenes"][0]["claim_ids"] = ["unknown"]
    assert any("valid claim" in error for error in validate_event_script(script, research()))


def test_author_can_report_insufficient_evidence():
    assert any("insufficient evidence" in error for error in validate_event_script(
        {"insufficient_evidence": True, "reason": "Too few distinct facts"}, research()))
