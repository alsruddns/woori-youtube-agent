from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import wave
from pathlib import Path
from fractions import Fraction
from typing import Any


def synthesize_scenes(scenes: list[dict[str, Any]], output_dir: Path, *, voice: str = "af_heart", language_code: str = "a", engine: str = "kokoro") -> list[Path]:
    """Synthesize narration via local Kokoro; weights/model are downloaded by Kokoro on first use."""
    if engine != "kokoro":
        raise RuntimeError(f"TTS engine is not installed or configured: {engine}")
    try:
        from kokoro import KPipeline
        import soundfile as sf
    except ImportError as exc:
        raise RuntimeError("Kokoro and soundfile are required for local TTS.") from exc
    output_dir.mkdir(parents=True, exist_ok=True)
    pipeline = KPipeline(lang_code=language_code)
    files = []
    for index, scene in enumerate(scenes, start=1):
        segments = [(text, audio) for text, _, audio in pipeline(
            scene["narration"], voice=voice, split_pattern=r"(?<=[.!?])\s+")]
        chunks = [audio for _, audio in segments]
        if not chunks:
            raise RuntimeError(f"Kokoro returned no audio for scene {index}.")
        import numpy as np
        audio = np.concatenate(chunks)
        path = output_dir / f"scene-{index:03d}.wav"
        sf.write(path, audio, 24000)
        offset = 0
        timings = []
        for text, chunk in segments:
            end = offset + len(chunk)
            timings.append({"start": offset / 24000, "end": end / 24000, "text": text})
            offset = end
        path.with_suffix(".timings.json").write_text(json.dumps(timings, ensure_ascii=False), encoding="utf-8")
        files.append(path)
    return files


def create_chart(values: list[tuple[str, float]], output: Path, *, title: str, locale: str = "en-US") -> Path:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError("Matplotlib is required for chart generation.") from exc
    labels, numbers = zip(*values)
    figure, axis = plt.subplots(figsize=(12, 6), dpi=160)
    axis.plot(labels, numbers, color="#32a3ff", linewidth=3, marker="o")
    axis.set_title(title, fontsize=20)
    axis.grid(alpha=0.2)
    figure.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, facecolor="#101827", edgecolor="none")
    plt.close(figure)
    return output


def render_video(script: dict[str, Any], audio_files: list[Path], output: Path, *, ffmpeg: str = "ffmpeg", width: int = 1920, height: int = 1080, burn_subtitles: bool = True) -> Path:
    if shutil.which(ffmpeg) is None:
        raise RuntimeError(f"FFmpeg executable not found: {ffmpeg}")
    scenes = script["scenes"]
    if len(scenes) != len(audio_files):
        raise ValueError("Each scene must have a corresponding narration audio file.")
    if not scenes:
        raise ValueError("At least one scene is required.")
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.parent / "render-scenes"
    temp.mkdir(exist_ok=True)
    rendered = []
    subtitle_cues: list[tuple[float, float, str]] = []
    elapsed = 0.0
    for index, (scene, audio) in enumerate(zip(scenes, audio_files), start=1):
        # Text cards avoid unlicensed news footage; later scene assets can replace these.
        from PIL import Image, ImageDraw, ImageFont, ImageOps
        asset = scene.get("asset")
        if asset:
            from .assets import validate_scene_assets
            asset_errors = validate_scene_assets([scene])
            if asset_errors:
                raise ValueError("Asset gate: " + "; ".join(asset_errors))
            with Image.open(asset["path"]) as source:
                image = ImageOps.fit(source.convert("RGB"), (width, height))
            if not asset.get("precomposed"):
                overlay = Image.new("RGBA", (width, height), (0, 0, 0, 105))
                image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
        else:
            image = Image.new("RGB", (width, height), "#101827")
        draw = ImageDraw.Draw(image)
        # Visual direction is for production, not audience-facing caption text.
        text = str(scene.get("on_screen_text", ""))[:200]
        if not asset or not asset.get("precomposed"):
            draw.text((90, 100), script.get("title", "Daily Briefing"), fill="white")
        if type(scene.get("rank")) is int and 1 <= scene["rank"] <= 5:
            try:
                rank_font = ImageFont.truetype("arialbd.ttf", max(36, width // 6))
            except OSError:
                rank_font = ImageFont.load_default(size=max(36, width // 6))
            draw.text((width // 10, height // 5), f"#{scene['rank']}", fill="#7dd3fc", font=rank_font,
                      stroke_width=2, stroke_fill="#101827")
        draw.multiline_text((90, height // 2), text, fill="#93c5fd", font_size=44, spacing=18)
        still_tmp = temp / f"{index:03d}.png"
        image.save(still_tmp)
        clip = temp / f"{index:03d}.mp4"
        with wave.open(str(audio), "rb") as wav:
            duration = wav.getnframes() / wav.getframerate()
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError(f"Scene {index} has empty narration audio.")
        scene_cues = _scene_cues(audio, str(scene.get("narration", "")), duration)
        subtitle_cues.extend((elapsed + start, elapsed + end, text) for start, end, text in scene_cues)
        srt_path = temp / f"{index:03d}.srt"
        srt_path.write_text(_srt(scene_cues), encoding="utf-8")
        subtitle_filter_path = str(srt_path.resolve()).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
        style = "Fontsize=11,Outline=1,Alignment=2,MarginV=48,MarginL=30,MarginR=30" if height > width else "Fontsize=22,Outline=2,MarginV=45"
        # Slow camera movement and short transitions; captions remain screen-anchored.
        fade_out = max(0.0, duration - 0.25)
        filters = (f"zoompan=z='min(zoom+0.00035,1.08)':d=1:s={width}x{height}:fps=30,"
                   f"fade=t=in:st=0:d=0.25,fade=t=out:st={fade_out:.3f}:d=0.25")
        if burn_subtitles:
            filters += f",subtitles='{subtitle_filter_path}':force_style='{style}'"
        subprocess.run([ffmpeg, "-y", "-loop", "1", "-i", str(still_tmp), "-i", str(audio), "-c:v", "libx264",
                        "-vf", filters,
                        "-r", "30", "-c:a", "aac", "-b:a", "192k", "-pix_fmt", "yuv420p", "-shortest", str(clip)],
                       check=True, capture_output=True)
        rendered.append(clip)
        elapsed += _probe_duration(clip, ffmpeg)
    manifest = temp / "concat.txt"
    manifest.write_text("\n".join(f"file '{p.name}'" for p in rendered), encoding="utf-8")
    subprocess.run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(manifest),
                    "-c:v", "libx264", "-r", "30", "-fps_mode", "cfr", "-pix_fmt", "yuv420p",
                    "-c:a", "copy", str(output)], check=True, capture_output=True)
    output.with_suffix(".srt").write_text(_srt(subtitle_cues), encoding="utf-8")
    return output


def _probe_duration(path: Path, ffmpeg: str) -> float:
    binary = Path(ffmpeg)
    sibling = binary.with_name("ffprobe.exe" if binary.suffix.lower() == ".exe" else "ffprobe")
    probe = str(sibling) if sibling.is_file() else shutil.which("ffprobe")
    if not probe:
        raise RuntimeError("ffprobe is required to align concatenated subtitles.")
    result = subprocess.run([probe, "-v", "error", "-show_entries", "format=duration", "-of",
                             "default=noprint_wrappers=1:nokey=1", str(path)],
                            capture_output=True, text=True, check=True)
    duration = float(result.stdout.strip())
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Rendered scene has invalid duration.")
    return duration


def _scene_cues(audio: Path, narration: str, duration: float) -> list[tuple[float, float, str]]:
    """Use actual TTS chunk boundaries; fallback timings remain approximate."""
    timing_path = audio.with_suffix(".timings.json")
    if timing_path.exists():
        try:
            timings = json.loads(timing_path.read_text(encoding="utf-8"))
            cues = [(float(item["start"]), float(item["end"]), str(item["text"]).strip()) for item in timings]
            if (not cues or abs(cues[0][0]) > 0.01 or abs(cues[-1][1] - duration) > 0.05
                    or any(not text or not math.isfinite(start) or not math.isfinite(end)
                           or start < 0 or end <= start or end > duration + 0.05
                           for start, end, text in cues)
                    or any(abs(a[1] - b[0]) > 0.01 for a, b in zip(cues, cues[1:]))):
                raise ValueError("Invalid timing boundaries")
            return _split_long_cues(cues)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid narration timing file: {timing_path}") from exc
    words = narration.split()
    groups = [words[offset:offset + 9] for offset in range(0, len(words), 9)]
    if not groups:
        raise ValueError("Narration text is empty")
    slot = duration / len(groups)
    return [(i * slot, (i + 1) * slot, " ".join(group)) for i, group in enumerate(groups)]


def _split_long_cues(cues: list[tuple[float, float, str]]) -> list[tuple[float, float, str]]:
    """Keep real TTS chunk bounds; sub-cue timing is an approximation, not forced alignment."""
    result = []
    for start, end, text in cues:
        words = text.split()
        groups = [words[i:i + 6] for i in range(0, len(words), 6)]
        weights = [sum(len(word) for word in group) for group in groups]
        total = sum(weights)
        cursor = start
        for index, (group, weight) in enumerate(zip(groups, weights)):
            next_time = end if index == len(groups) - 1 else cursor + (end - start) * weight / total
            result.append((cursor, next_time, " ".join(group)))
            cursor = next_time
    return result


def _srt_time(seconds: float) -> str:
    milliseconds = int((seconds - int(seconds)) * 1000)
    whole = int(seconds)
    hours, remainder = divmod(whole, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02}:{minutes:02}:{secs:02},{milliseconds:03}"


def _srt(cues: list[tuple[float, float, str]]) -> str:
    return "\n\n".join(f"{index}\n{_srt_time(start)} --> {_srt_time(end)}\n{text}"
                       for index, (start, end, text) in enumerate(cues, start=1)) + "\n"


def create_thumbnail(title: str, output: Path, *, subtitle: str = "DAILY MARKET BRIEFING") -> Path:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        raise RuntimeError("Pillow is required for thumbnail generation.") from exc
    image = Image.new("RGB", (1280, 720), "#101827")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1280, 16), fill="#38bdf8")
    try:
        label_font = ImageFont.truetype("arialbd.ttf", 30)
    except OSError:
        label_font = ImageFont.load_default(size=30)
    draw.text((72, 90), subtitle, fill="#7dd3fc", font=label_font)
    words = title.split()
    if not words:
        raise ValueError("Thumbnail title is empty.")
    for size in range(76, 27, -4):
        try:
            font = ImageFont.truetype("arialbd.ttf", size)
        except OSError:
            font = ImageFont.load_default(size=size)
        lines = []
        for word in words:
            line = (lines[-1] + " " + word) if lines else word
            if lines and draw.textlength(line, font=font) > 1136:
                lines.append(word)
            elif lines:
                lines[-1] = line
            else:
                lines.append(word)
        text = "\n".join(lines)
        bounds = draw.multiline_textbbox((72, 180), text, font=font, spacing=14, stroke_width=1)
        if bounds[2] <= 1208 and bounds[3] <= 650:
            break
    else:
        raise ValueError("Thumbnail title is too long to fit legibly.")
    draw.multiline_text((72, 180), text, fill="white", font=font, spacing=14, stroke_width=1)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, "JPEG", quality=90, optimize=True)
    return output


def validate_video(path: Path, *, ffmpeg: str = "ffmpeg", minimum_seconds: int = 480,
                   maximum_seconds: int = 1080, width: int = 1920, height: int = 1080) -> list[str]:
    if not path.exists() or path.stat().st_size < 100_000:
        return ["Rendered video is missing or too small."]
    ffmpeg_path = Path(ffmpeg)
    sibling = ffmpeg_path.with_name("ffprobe.exe" if ffmpeg_path.suffix.lower() == ".exe" else "ffprobe")
    probe = str(sibling) if sibling.is_file() else shutil.which("ffprobe")
    if not probe:
        return ["ffprobe is not installed; media validation cannot pass."]
    result = subprocess.run([probe, "-v", "error", "-show_entries",
                             "format=duration:stream=codec_type,width,height,avg_frame_rate", "-of", "json", str(path)],
                            capture_output=True, text=True)
    if result.returncode:
        return ["ffprobe could not read the video."]
    try:
        data = json.loads(result.stdout)
        duration = float(data["format"]["duration"])
        streams = data.get("streams", [])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return ["ffprobe did not provide valid media metadata."]
    errors = []
    if not math.isfinite(duration) or duration < minimum_seconds:
        errors.append(f"Video duration {duration:.1f}s is below {minimum_seconds}s.")
    elif duration > maximum_seconds:
        errors.append(f"Video duration {duration:.1f}s exceeds {maximum_seconds}s.")
    videos = [s for s in streams if s.get("codec_type") == "video"]
    if not videos or videos[0].get("width") != width or videos[0].get("height") != height:
        errors.append(f"Video resolution must be {width}x{height}.")
    if videos:
        try:
            fps = Fraction(videos[0].get("avg_frame_rate", "0/1"))
            if fps != 30:
                raise ValueError
        except (ValueError, ZeroDivisionError, TypeError):
            errors.append("Video frame rate must be 30 fps.")
    if not any(s.get("codec_type") == "audio" for s in streams):
        errors.append("Video has no audio stream.")
    return errors


def validate_video_content(path: Path, *, ffmpeg: str = "ffmpeg") -> list[str]:
    """Fully decode both streams and detect inaudible mean audio level.

    This cannot establish factual accuracy, subtitle accuracy, or visual quality.
    """
    result = subprocess.run([ffmpeg, "-hide_banner", "-v", "info", "-xerror", "-i", str(path),
                             "-map", "0:v:0", "-map", "0:a:0", "-af", "volumedetect",
                             "-f", "null", "-"], capture_output=True, text=True)
    if result.returncode:
        return ["Full audio/video decode failed."]
    match = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?|-inf)\s*dB", result.stderr)
    if not match:
        return ["Could not measure audio level."]
    if match.group(1) == "-inf" or float(match.group(1)) < -55:
        return ["Audio is silent or too quiet to verify."]
    return []
