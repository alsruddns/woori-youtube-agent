from __future__ import annotations

import json
import math
import shutil
import subprocess
from pathlib import Path
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
        chunks = [audio for _, _, audio in pipeline(scene["narration"], voice=voice)]
        if not chunks:
            raise RuntimeError(f"Kokoro returned no audio for scene {index}.")
        import numpy as np
        audio = np.concatenate(chunks)
        path = output_dir / f"scene-{index:03d}.wav"
        sf.write(path, audio, 24000)
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


def render_video(script: dict[str, Any], audio_files: list[Path], output: Path, *, ffmpeg: str = "ffmpeg", width: int = 1920, height: int = 1080) -> Path:
    if shutil.which(ffmpeg) is None:
        raise RuntimeError(f"FFmpeg executable not found: {ffmpeg}")
    scenes = script["scenes"]
    if len(scenes) != len(audio_files):
        raise ValueError("Each scene must have a corresponding narration audio file.")
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.parent / "render-scenes"
    temp.mkdir(exist_ok=True)
    rendered = []
    subtitle_cues: list[tuple[float, float, str]] = []
    elapsed = 0.0
    for index, (scene, audio) in enumerate(zip(scenes, audio_files), start=1):
        still = temp / f"{index:03d}.png"
        # Text cards avoid unlicensed news footage; later scene assets can replace these.
        from PIL import Image, ImageDraw, ImageFont
        image = Image.new("RGB", (width, height), "#101827")
        draw = ImageDraw.Draw(image)
        text = str(scene.get("visual", ""))[:200]
        draw.text((90, 100), script.get("title", "Daily Briefing"), fill="white")
        draw.multiline_text((90, height // 2), text, fill="#93c5fd", font_size=44, spacing=18)
        still_tmp = temp / f"{index:03d}.png"
        image.save(still_tmp)
        clip = temp / f"{index:03d}.mp4"
        duration = max(1, int(scene.get("duration_seconds", 1)))
        words = str(scene.get("narration", "")).split()
        group_size = 9
        groups = [words[offset:offset + group_size] for offset in range(0, len(words), group_size)] or [[]]
        slot = duration / len(groups)
        for cue_index, group in enumerate(groups):
            subtitle_cues.append((elapsed + cue_index * slot, elapsed + (cue_index + 1) * slot, " ".join(group)))
        srt_path = temp / f"{index:03d}.srt"
        srt_path.write_text(_srt([(i * slot, (i + 1) * slot, " ".join(group)) for i, group in enumerate(groups)]), encoding="utf-8")
        subtitle_filter_path = str(srt_path.resolve()).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
        subprocess.run([ffmpeg, "-y", "-loop", "1", "-i", str(still_tmp), "-i", str(audio), "-c:v", "libx264",
                        "-tune", "stillimage", "-vf", f"subtitles='{subtitle_filter_path}':force_style='Fontsize=22,Outline=2,MarginV=45'",
                        "-c:a", "aac", "-b:a", "192k", "-pix_fmt", "yuv420p", "-shortest", str(clip)],
                       check=True, capture_output=True)
        rendered.append(clip)
        elapsed += duration
    manifest = temp / "concat.txt"
    manifest.write_text("\n".join(f"file '{p.name}'" for p in rendered), encoding="utf-8")
    subprocess.run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(manifest), "-c", "copy", str(output)], check=True, capture_output=True)
    return output


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
    draw.text((72, 110), subtitle, fill="#7dd3fc")
    draw.multiline_text((72, 210), title[:110], fill="white", spacing=14, font_size=64, stroke_width=1)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, "JPEG", quality=90, optimize=True)
    return output


def validate_video(path: Path, *, ffmpeg: str = "ffmpeg", minimum_seconds: int = 60) -> list[str]:
    if not path.exists() or path.stat().st_size < 100_000:
        return ["Rendered video is missing or too small."]
    probe = shutil.which("ffprobe")
    if not probe:
        return ["ffprobe is not installed; media validation cannot pass."]
    result = subprocess.run([probe, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)], capture_output=True, text=True)
    if result.returncode:
        return ["ffprobe could not read the video."]
    duration = float(json.loads(result.stdout)["format"]["duration"])
    return [] if duration >= minimum_seconds else [f"Video duration {duration:.1f}s is below {minimum_seconds}s."]
