"""Render a prepared three-format script after explicit research and asset gates."""
import json
import wave
from pathlib import Path

from .assets import validate_scene_assets
from .content_script import validate_content_script
from .content_types import ContentType, SPECS
from .event_production import ProductionBlocked
from .media import _probe_duration, create_thumbnail, render_video, synthesize_scenes, validate_video, validate_video_content


def render_content(kind, topics, research, script, assets, output_dir: Path, *, ffmpeg: str,
                   period=None, ranking_basis=None, thumbnail_asset=None) -> dict:
    kind = ContentType(kind)
    spec = SPECS[kind]
    errors = validate_content_script(kind, topics, research, script, period=period, ranking_basis=ranking_basis)
    if errors:
        raise ProductionBlocked("Script gate: " + "; ".join(errors))
    scenes = script["scenes"]
    if not isinstance(assets, list) or len(assets) != len(scenes):
        raise ProductionBlocked("Each scene requires one reviewed image asset.")
    scenes = [{**scene, "asset": asset} for scene, asset in zip(scenes, assets)]
    errors = validate_scene_assets(scenes)
    if errors:
        raise ProductionBlocked("Asset gate: " + "; ".join(errors))
    if thumbnail_asset is not None:
        errors = validate_scene_assets([{"asset": thumbnail_asset}])
        if errors:
            raise ProductionBlocked("Thumbnail asset gate: " + "; ".join(errors))
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ProductionBlocked("Output directory is not empty; preserve existing artifacts.")
    output_dir.mkdir(parents=True, exist_ok=True)
    audio = synthesize_scenes(scenes, output_dir / "audio")
    seconds = 0.0
    for path in audio:
        with wave.open(str(path), "rb") as wav:
            seconds += wav.getnframes() / wav.getframerate()
    report = {"content_type": kind.value, "narration_seconds": seconds,
              "editorial_review_required": True, "automated_media_checks_passed": False}
    report_path = output_dir / "production.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if not spec.min_seconds <= seconds <= spec.max_seconds:
        raise ProductionBlocked(f"Narration is {seconds:.1f}s, outside {spec.min_seconds}–{spec.max_seconds}s.")
    video = render_video({**script, "scenes": scenes}, audio, output_dir / "final.mp4",
                         ffmpeg=ffmpeg, width=spec.width, height=spec.height, burn_subtitles=False)
    errors = validate_video(video, ffmpeg=ffmpeg, minimum_seconds=spec.min_seconds,
                            maximum_seconds=spec.max_seconds, width=spec.width, height=spec.height)
    if not errors:
        errors = validate_video_content(video, ffmpeg=ffmpeg)
    if errors:
        raise ProductionBlocked("Media gate: " + "; ".join(errors))
    if thumbnail_asset is not None:
        from .visual_cards import create_news_thumbnail
        thumbnail = create_news_thumbnail(output_dir / "thumbnail.jpg", background=Path(thumbnail_asset["path"]),
                                          headline=script["title"], badge="NOW TRENDS")
    else:
        thumbnail = create_thumbnail(script["title"], output_dir / "thumbnail.jpg", subtitle="NOW TRENDS")
    report.update({"video": str(video), "thumbnail": str(thumbnail),
                   "video_seconds": _probe_duration(video, ffmpeg), "automated_media_checks_passed": True})
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
