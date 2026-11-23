from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from .models import ResearchPackage, VideoScript


def script_prompt(package: ResearchPackage, locale: str, language_name: str, target_minutes: int,
                  disclaimer: str = "This is news commentary, not investment advice.") -> str:
    research = json.dumps(package.to_dict(), ensure_ascii=False, indent=2)
    return f"""Create a {target_minutes}-minute {language_name} video script in locale {locale} from the research below.
Return only JSON with keys title, description, language, scenes, claims.
Each scene: narration, visual, duration_seconds. Each claim: text, source_urls.
For every claim include evidence_text as a short exact excerpt copied from the cited item's
title or feed summary. A claim without a matching excerpt must not appear.
Cover both economic and political developments when supported by sources. Never invent facts,
quotes, figures, or causal links. Distinguish reported fact from analysis. Include this localized disclaimer verbatim: {disclaimer}
Cite every factual claim with
one or more exact source URLs from the package. Make the script original; do not reproduce article prose.
Research package:\n{research}"""


def validate_script(data: dict[str, Any], package: ResearchPackage, *, target_minutes: int = 15,
                    require_categories: set[str] | None = None,
                    disclaimer: str = "not investment advice") -> list[str]:
    errors: list[str] = []
    for key in ("title", "description", "language", "scenes", "claims"):
        if key not in data:
            errors.append(f"Missing required field: {key}")
    scenes = data.get("scenes", [])
    claims = data.get("claims", [])
    if not isinstance(scenes, list) or not scenes:
        errors.append("At least one scene is required.")
        scenes = []
    if not isinstance(claims, list) or not claims:
        errors.append("At least one source-linked claim is required.")
        claims = []
    seconds = 0
    for index, scene in enumerate(scenes):
        if not isinstance(scene, dict) or not scene.get("narration", "").strip():
            errors.append(f"Scene {index + 1} has no narration.")
            continue
        if not scene.get("visual"):
            errors.append(f"Scene {index + 1} has no visual direction.")
        try:
            duration = int(scene.get("duration_seconds", 0))
            if duration < 1:
                raise ValueError
            seconds += duration
        except (ValueError, TypeError):
            errors.append(f"Scene {index + 1} has invalid duration_seconds.")
    known_urls = {item.url for item in package.items}
    for index, claim in enumerate(claims):
        if not isinstance(claim, dict) or not claim.get("text"):
            errors.append(f"Claim {index + 1} has no text.")
            continue
        sources = claim.get("source_urls", [])
        if not sources:
            errors.append(f"Claim {index + 1} has no source URL.")
        elif any(url not in known_urls for url in sources):
            errors.append(f"Claim {index + 1} cites a URL outside the research package.")
        evidence = str(claim.get("evidence_text", "")).strip()
        matching_items = [item for item in package.items if item.url in sources]
        valid_evidence = evidence and any(evidence.casefold() in f"{item.title} {item.summary}".casefold() for item in matching_items)
        if not valid_evidence:
            errors.append(f"Claim {index + 1} has no exact evidence excerpt in its cited source item.")
        else:
            def numbers(text: str) -> set[str]:
                return {match.replace(",", "") for match in re.findall(r"(?<![A-Za-z])\d+(?:,\d{3})*(?:\.\d+)?", text)}
            unsupported_numbers = numbers(str(claim["text"])) - numbers(evidence)
            if unsupported_numbers:
                errors.append(f"Claim {index + 1} contains figures absent from its source excerpt: {', '.join(sorted(unsupported_numbers))}.")
    for category in require_categories or set():
        category_urls = {item.url for item in package.items if item.category == category}
        if category_urls and not any(category_urls.intersection(claim.get("source_urls", [])) for claim in claims if isinstance(claim, dict)):
            errors.append(f"Script contains no source-linked claim from the required {category} category.")
    if seconds < target_minutes * 60 * 0.9:
        errors.append(f"Script is too short: {seconds}s for a {target_minutes}-minute target.")
    if disclaimer.casefold() not in data.get("description", "").casefold():
        errors.append("Description must include the channel's localized disclaimer verbatim.")
    return errors


def run_codex(prompt: str, output_path: Path, *, command: str = "codex", timeout: int = 1800) -> dict[str, Any]:
    """Invoke an installed, signed-in Codex CLI session; never uses an OpenAI API key."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run([command, "exec", "--sandbox", "read-only",
                             "--output-last-message", str(output_path), "-"],
                            input=prompt, capture_output=True, text=True, timeout=timeout, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"Codex CLI failed ({result.returncode}): {result.stderr[-2000:]}")
    try:
        return json.loads(output_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("Codex did not write valid JSON output.") from exc
