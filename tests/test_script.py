from woori_youtube.models import NewsItem, ResearchPackage
from woori_youtube.script import validate_script


def _package():
    return ResearchPackage("us-economy", "2026-11-23", [
        NewsItem("Fed held rates steady", "https://fed.gov/item", "fed", summary="The Fed held interest rates steady today.", content_hash="1"),
        NewsItem("Jobs report", "https://bls.gov/item", "bls", summary="Payroll growth was reported today.", content_hash="2"),
    ])


def test_script_gate_rejects_unlinked_claim_and_short_duration():
    data = {"title": "Daily briefing", "description": "News commentary, not investment advice.", "language": "en-US",
            "scenes": [{"narration": "A short sentence.", "visual": "Market chart", "duration_seconds": 100}],
            "claims": [{"text": "A claim", "source_urls": ["https://evil.example/fake"], "evidence_text": "invented"}]}
    errors = validate_script(data, _package(), target_minutes=15)
    assert any("outside the research package" in error for error in errors)
    assert any("exact evidence excerpt" in error for error in errors)
    assert any("too short" in error for error in errors)


def test_script_gate_accepts_traceable_structure_and_target_duration():
    data = {"title": "Daily briefing", "description": "News commentary, not investment advice.", "language": "en-US",
            "scenes": [{"narration": "A narration", "visual": "Market chart", "duration_seconds": 810}],
            "claims": [{"text": "Fed held rates steady", "source_urls": ["https://fed.gov/item"],
                        "evidence_text": "The Fed held interest rates steady today."}]}
    assert validate_script(data, _package(), target_minutes=15) == []


def test_script_gate_rejects_numeric_claim_not_in_evidence():
    data = {"title": "Daily briefing", "description": "News commentary, not investment advice.", "language": "en-US",
            "scenes": [{"narration": "A narration", "visual": "Market chart", "duration_seconds": 810}],
            "claims": [{"text": "The Fed held rates at 4.5%.", "source_urls": ["https://fed.gov/item"],
                        "evidence_text": "The Fed held interest rates steady today."}]}
    assert any("figures absent" in error for error in validate_script(data, _package(), target_minutes=15))


def test_script_gate_requires_political_coverage_when_researched():
    package = _package()
    package.items.append(NewsItem("House approves bill", "https://house.gov/bill", "house",
                                 summary="The House approved the bill today.", category="politics", content_hash="3"))
    data = {"title": "Daily briefing", "description": "News commentary, not investment advice.", "language": "en-US",
            "scenes": [{"narration": "A narration", "visual": "Market chart", "duration_seconds": 810}],
            "claims": [{"text": "The Fed held rates steady", "source_urls": ["https://fed.gov/item"],
                        "evidence_text": "The Fed held interest rates steady today."}]}
    errors = validate_script(data, package, target_minutes=15, require_categories={"economy", "politics"})
    assert any("required politics category" in error for error in errors)
