import json
import shutil
import wave

import numpy as np
import pytest

from woori_youtube import subtitle_alignment as alignment


def write_wav(path, samples):
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(np.asarray(samples, dtype="<i2").tobytes())


def test_alignment_finds_shifted_scene_starts_and_retains_chunks(tmp_path, monkeypatch):
    rng = np.random.default_rng(5)
    a = rng.integers(-3000, 3000, 96000, dtype=np.int16)
    b = rng.integers(-3000, 3000, 96000, dtype=np.int16)
    first, second = tmp_path / "a.wav", tmp_path / "b.wav"
    write_wav(first, a)
    write_wav(second, b)
    for file, text in [(first, "First sentence."), (second, "Second sentence.")]:
        file.with_suffix(".timings.json").write_text(json.dumps([{"start": 0, "end": 4, "text": text}]), encoding="utf-8")
    mixed = tmp_path / "mixed.wav"
    write_wav(mixed, np.concatenate([np.zeros(4800, dtype=np.int16), a, np.zeros(7200, dtype=np.int16), b]))
    video = tmp_path / "video.mp4"
    video.write_bytes(b"placeholder")
    monkeypatch.setattr(alignment.subprocess, "run", lambda args, **kw: shutil.copyfile(mixed, args[-1]))
    result = alignment.align_tts_subtitles(video, [first, second], tmp_path / "result.srt", ffmpeg="ffmpeg")
    assert abs(result[0]["start_seconds"] - 0.2) < 0.01
    assert abs(result[1]["start_seconds"] - 4.5) < 0.01
    assert "00:00:04,500" in (tmp_path / "result.srt").read_text(encoding="utf-8")


def test_alignment_rejects_unrelated_audio():
    rng = np.random.default_rng(1)
    with pytest.raises(ValueError, match="confidence"):
        alignment._match(rng.normal(0, 3000, 48000), rng.normal(0, 3000, 200000), 1)
