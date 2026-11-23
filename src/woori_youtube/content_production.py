"""Render a prepared three-format script after explicit research and asset gates."""
import json
import shutil
import wave
from pathlib import Path

from .assets import validate_scene_assets
from .content_script import validate_content_script
from .content_types import ContentType, SPECS
from .event_production import ProductionBlocked
from .media import _probe_duration, create_thumbnail, render_video, synthesize_scenes, validate_video, validate_video_content


def render_content(kind, topics, research, script, assets, output_dir: Path, *, ffmpeg: str,
                   period=None, ranking_basis=None, thumbnail_asset=None, audio_profile="original_preview") -> dict:
    kind = ContentType(kind)
    spec = SPECS[kind]
    if audio_profile not in {"original_preview", "off"}:
        raise ProductionBlocked("Unsupported audio profile")
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
              "editorial_review_required": True, "automated_media_checks_passed": False,
              "visual_assets": assets}
    report_path = output_dir / "production.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if not spec.min_seconds <= seconds <= spec.max_seconds:
        raise ProductionBlocked(f"Narration is {seconds:.1f}s, outside {spec.min_seconds}–{spec.max_seconds}s.")
    sensitive = any(item.get("sensitivity") == "sensitive" for item in research.values() if isinstance(item, dict))
    use_music = audio_profile == "original_preview" and not sensitive
    raw_video = output_dir / ("narration-only.mp4" if use_music else "final.mp4")
    video = render_video({**script, "scenes": scenes}, audio, raw_video,
                         ffmpeg=ffmpeg, width=spec.width, height=spec.height, burn_subtitles=False)
    if use_music:
        from .audio_brand import make_original_bed, make_original_effect, mix_voice_bed
        bed = make_original_bed(output_dir / "original-bed.wav", kind)
        signature = make_original_effect(output_dir / "signature.wav", signature=True)
        effect = make_original_effect(output_dir / "transition.wav")
        clips = sorted((output_dir / "render-scenes").glob("*.mp4"))
        cues = []
        elapsed = 0.0
        for clip in clips[:-1]:
            elapsed += _probe_duration(clip, ffmpeg)
            cues.append(elapsed)
        if len(cues) > 20:
            cues = []  # Avoid unbounded filter graphs; do not affect production.
        video = mix_voice_bed(raw_video, bed, output_dir / "final.mp4", ffmpeg=ffmpeg,
                              signature=signature, effect=effect, cue_times=tuple(cues))
        shutil.copyfile(raw_video.with_suffix(".srt"), video.with_suffix(".srt"))
    report["audio_profile"] = "original_preview" if use_music else "off"
    report["audio_review_required"] = use_music
    if sensitive and audio_profile != "off":
        report["audio_fallback_reason"] = "Sensitive event: background music disabled for review."
    errors = validate_video(video, ffmpeg=ffmpeg, minimum_seconds=spec.min_seconds,
                            maximum_seconds=spec.max_seconds, width=spec.width, height=spec.height)
    if not errors:
        errors = validate_video_content(video, ffmpeg=ffmpeg)
    if errors:
        raise ProductionBlocked("Media gate: " + "; ".join(errors))
    from .subtitle_alignment import align_tts_subtitles
    aligned_srt = output_dir / "final.aligned.srt"
    try:
        alignment = align_tts_subtitles(video, audio, aligned_srt, ffmpeg=ffmpeg)
    except (ValueError, OSError) as exc:
        raise ProductionBlocked("Subtitle alignment gate: " + str(exc)) from exc
    if thumbnail_asset is not None:
        from .visual_cards import create_news_thumbnail
        thumbnail = create_news_thumbnail(output_dir / "thumbnail.jpg", background=Path(thumbnail_asset["path"]),
                                          headline=script["title"], badge="NOW TRENDS")
    else:
        thumbnail = create_thumbnail(script["title"], output_dir / "thumbnail.jpg", subtitle="NOW TRENDS")
    report.update({"video": str(video), "thumbnail": str(thumbnail),
                   "video_seconds": _probe_duration(video, ffmpeg), "automated_media_checks_passed": True,
                   "aligned_srt": str(aligned_srt), "caption_alignment": alignment,
                   "caption_editorial_review_required": True})
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
