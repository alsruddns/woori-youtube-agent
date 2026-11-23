"""Explicit local render stage for a researched, source-linked event."""
from __future__ import annotations

import json
import wave
from pathlib import Path

from .assets import validate_scene_assets
from .event_script import validate_event_script
from .media import create_thumbnail, render_video, synthesize_scenes, validate_video, validate_video_content


class ProductionBlocked(RuntimeError):
    pass


def render_event(research: dict, script: dict, assets: list[dict], output_dir: Path, *, ffmpeg: str) -> dict:
    errors = validate_event_script(script, research)
    scenes = script.get("scenes", [])
    if errors:
        raise ProductionBlocked("Script gate: " + "; ".join(errors))
    if not isinstance(assets, list) or len(assets) != len(scenes):
        raise ProductionBlocked("Each scene requires one reviewed image asset.")
    scenes = [{**scene, "asset": asset} for scene, asset in zip(scenes, assets)]
    errors = validate_scene_assets(scenes)
    if errors:
        raise ProductionBlocked("Asset gate: " + "; ".join(errors))
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ProductionBlocked("Output directory is not empty; choose a new directory to preserve artifacts.")
    output_dir.mkdir(parents=True, exist_ok=True)
    audio_files = synthesize_scenes(scenes, output_dir / "audio")
    duration = 0.0
    for audio in audio_files:
        with wave.open(str(audio), "rb") as wav:
            duration += wav.getnframes() / wav.getframerate()
    report = {"narration_seconds": duration, "editorial_review_required": True,
              "note": "Automated checks cannot verify source accuracy, rights or visual quality."}
    (output_dir / "production.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if not 480 <= duration <= 1080:
        raise ProductionBlocked(f"Actual narration is {duration:.1f}s; expected 480–1080s. Revise the script without padding.")
    video = render_video({**script, "scenes": scenes}, audio_files, output_dir / "final.mp4", ffmpeg=ffmpeg)
    errors = validate_video(video, ffmpeg=ffmpeg)
    if not errors:
        errors = validate_video_content(video, ffmpeg=ffmpeg)
    if errors:
        raise ProductionBlocked("Video gate: " + "; ".join(errors))
    thumbnail = create_thumbnail(script["title"], output_dir / "thumbnail.jpg", subtitle="NOW TRENDS")
    report.update({"video": str(video), "thumbnail": str(thumbnail), "automated_media_checks_passed": True})
    (output_dir / "production.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
