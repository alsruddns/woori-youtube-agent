"""Locally synthesized demonstration bed and voice-aware FFmpeg mixing."""
from __future__ import annotations

import json
import subprocess
import wave
from pathlib import Path

import numpy as np

from .content_types import ContentType
from .media import _probe_duration


def make_original_bed(path: Path, kind: ContentType, *, sample_rate: int = 48000) -> Path:
    """Generate a simple synthesized loop from mathematical tones, no external recordings."""
    kind = ContentType(kind)
    bpm = {ContentType.MAIN_NEWS: 108, ContentType.SINGLE_SHORT: 132, ContentType.TOP5_SHORT: 128}[kind]
    beats = 16
    count = round(sample_rate * beats * 60 / bpm)
    t = np.arange(count, dtype=np.float64) / sample_rate
    beat = np.mod(t * bpm / 60, 1.0)
    envelope = np.exp(-beat * 16)
    kick = np.sin(2 * np.pi * (63 * t - 5 * np.exp(-beat * 12))) * envelope
    notes = (110.0, 130.81, 164.81, 146.83)
    note = np.asarray(notes)[np.floor(t * bpm / 240).astype(int) % len(notes)]
    phase = np.cumsum(note) * (2 * np.pi / sample_rate)
    pulse = np.sin(phase) * np.exp(-np.mod(t * bpm / 30, 1.0) * 5)
    shimmer = np.sin(2 * np.pi * 880 * t) * np.exp(-np.mod(t * bpm / 30, 1.0) * 35)
    samples = np.clip(0.11 * kick + 0.055 * pulse + 0.01 * shimmer, -0.35, 0.35)
    # Short endpoint fades prevent clicks; a later production mix can crossfade loops.
    ramp = min(round(sample_rate * 0.03), count // 2)
    samples[:ramp] *= np.linspace(0, 1, ramp)
    samples[-ramp:] *= np.linspace(1, 0, ramp)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes((samples * 32767).astype("<i2").tobytes())
    path.with_suffix(".license.json").write_text(json.dumps({"origin": "locally synthesized tones",
        "external_samples": False, "commercial_use": "original generated test asset; review before publication",
        "content_type": kind.value, "bpm": bpm}, indent=2), encoding="utf-8")
    return path


def make_original_effect(path: Path, *, signature: bool = False, sample_rate: int = 48000) -> Path:
    duration = 2.0 if signature else 0.22
    samples = np.zeros(round(duration * sample_rate), dtype=np.float64)
    notes = (523.25, 659.25, 783.99, 987.77) if signature else (880.0,)
    for index, frequency in enumerate(notes):
        start = round(index * 0.36 * sample_rate)
        length = min(round((0.48 if signature else duration) * sample_rate), len(samples) - start)
        t = np.arange(length) / sample_rate
        envelope = np.sin(np.pi * np.arange(length) / length) ** 2
        samples[start:start + length] += 0.18 * np.sin(2 * np.pi * frequency * t) * envelope
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes((np.clip(samples, -0.5, 0.5) * 32767).astype("<i2").tobytes())
    path.with_suffix(".license.json").write_text(json.dumps({"origin": "locally synthesized tones",
        "external_samples": False, "commercial_use": "original generated test asset; review before publication",
        "kind": "signature" if signature else "transition"}, indent=2), encoding="utf-8")
    return path


def mix_voice_bed(video: Path, bed: Path, output: Path, *, ffmpeg: str, music_gain: float = 0.20,
                  signature: Path | None = None, effect: Path | None = None, cue_times: tuple[float, ...] = ()) -> Path:
    if not 0 <= music_gain <= 1:
        raise ValueError("music_gain must be between zero and one")
    if not video.is_file() or not bed.is_file() or output.exists():
        raise ValueError("Existing input files and a new output path are required")
    if signature and not signature.is_file() or effect and not effect.is_file():
        raise ValueError("Audio effect files must exist")
    duration = _probe_duration(video, ffmpeg)
    fade_start = max(0, duration - 0.8)
    if len(cue_times) > 20 or any(not 0 <= cue < duration for cue in cue_times) or (cue_times and not effect):
        raise ValueError("Invalid transition cues")
    filters = (f"[0:a]asplit=2[voice][side];[1:a]atrim=duration={duration:.3f},"
               f"volume={music_gain:.3f},afade=t=in:st=0:d=0.5,afade=t=out:st={fade_start:.3f}:d=0.8[music];"
               "[music][side]sidechaincompress=threshold=0.03:ratio=8:attack=30:release=350[duck];")
    inputs = ["[voice]", "[duck]"]
    extra_args = []
    input_index = 2
    if signature:
        extra_args += ["-i", str(signature)]
        filters += f"[{input_index}:a]volume=0.08[sig];"
        inputs.append("[sig]")
        input_index += 1
    if effect and cue_times:
        extra_args += ["-i", str(effect)]
        split = "".join(f"[raw{i}]" for i in range(len(cue_times)))
        filters += f"[{input_index}:a]asplit={len(cue_times)}{split};"
        for index, cue in enumerate(cue_times):
            delay = round(cue * 1000)
            filters += f"[raw{index}]volume=0.08,adelay={delay}:all=1[fx{index}];"
            inputs.append(f"[fx{index}]")
    filters += ("".join(inputs) + f"amix=inputs={len(inputs)}:duration=first:normalize=0,"
                "loudnorm=I=-16:TP=-2:LRA=11,alimiter=limit=0.70:level=0[mix]")
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([ffmpeg, "-y", "-v", "error", "-i", str(video), "-stream_loop", "-1", "-i", str(bed), *extra_args,
                    "-filter_complex", filters, "-map", "0:v:0", "-map", "[mix]", "-t", f"{duration:.3f}",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(output)],
                   check=True, capture_output=True)
    return output
