"""Align TTS chunk captions to a rendered video's decoded audio."""
from __future__ import annotations

import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np

from .media import _scene_cues, _srt


def _read_pcm(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as wav:
        if wav.getframerate() != 24000 or wav.getnchannels() != 1 or wav.getsampwidth() != 2:
            raise ValueError("Alignment requires mono 24 kHz 16-bit PCM audio")
        return np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").astype(np.float64)


def _match(reference: np.ndarray, final: np.ndarray, expected_seconds: float, *, search_seconds: float = 3) -> tuple[float, float]:
    """Match a short voice sample within a bounded window at 24 kHz."""
    rate = 24000
    reference = reference - reference.mean()
    if len(reference) < rate or np.linalg.norm(reference) < 1000:
        raise ValueError("Reference audio is too short or quiet to align")
    start = max(0, round((expected_seconds - search_seconds) * rate))
    end = min(len(final), round((expected_seconds + search_seconds) * rate) + len(reference))
    region = final[start:end]
    count = len(region) - len(reference) + 1
    if count <= 0:
        raise ValueError("Rendered audio is too short for alignment")
    nfft = 1 << ((len(region) + len(reference) - 1).bit_length())
    correlation = np.fft.irfft(np.fft.rfft(region, nfft) * np.conj(np.fft.rfft(reference, nfft)), nfft)[:count]
    squares = np.concatenate(([0.0], np.cumsum(region * region)))
    energy = squares[len(reference):] - squares[:-len(reference)]
    scores = np.abs(correlation) / np.maximum(np.sqrt(np.maximum(energy, 0)) * np.linalg.norm(reference), 1)
    index = int(np.argmax(scores))
    score = float(scores[index])
    if score < 0.70:
        raise ValueError(f"Voice alignment confidence is too low ({score:.2f})")
    return (start + index) / rate, score


def align_tts_subtitles(video: Path, audio_files: list[Path], output: Path, *, ffmpeg: str) -> list[dict]:
    if not video.is_file() or not audio_files or output.exists():
        raise ValueError("Existing video, narration files and a new SRT path are required")
    with tempfile.TemporaryDirectory(prefix="woori-caption-") as directory:
        decoded = Path(directory) / "audio.wav"
        subprocess.run([ffmpeg, "-v", "error", "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "24000",
                        "-c:a", "pcm_s16le", str(decoded)], check=True, capture_output=True)
        final = _read_pcm(decoded)
        expected, previous_end = 0.0, 0.0
        cues, checks = [], []
        for index, file in enumerate(audio_files, 1):
            reference = _read_pcm(file)
            duration = len(reference) / 24000
            sample_length = min(len(reference), 48000)
            start, confidence = _match(reference[:sample_length], final, expected)
            if start + 0.05 < previous_end:
                raise ValueError("Aligned narration scenes overlap")
            if duration > 3:
                # The last chunk can contain silence; use the strongest one-second window near its end.
                width = 24000
                starts = range(max(0, len(reference) - 3 * width), len(reference) - width + 1, width // 4)
                offset = max(starts, key=lambda pos: float(np.dot(reference[pos:pos + width], reference[pos:pos + width])))
                end_position = offset / 24000
                matched_end, end_confidence = _match(reference[offset:offset + width], final, start + end_position, search_seconds=0.5)
                if abs(matched_end - (start + end_position)) > 0.12:
                    raise ValueError("Narration timing changes within a scene")
                confidence = min(confidence, end_confidence)
            chunk_cues = _scene_cues(file, "", duration, split_long=False)
            cues.extend((start + a, start + b, text) for a, b, text in chunk_cues)
            checks.append({"scene": index, "start_seconds": round(start, 3), "confidence": round(confidence, 3)})
            previous_end = start + duration
            expected = previous_end
        if cues[-1][1] > len(final) / 24000 + 0.05:
            raise ValueError("Caption exceeds the rendered audio")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(_srt(cues), encoding="utf-8")
        return checks
