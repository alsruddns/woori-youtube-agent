import json
import wave
import pytest
from types import SimpleNamespace
from woori_youtube import media


def test_render_subtitles_use_actual_audio_duration(tmp_path, monkeypatch):
    audio = tmp_path / "voice.wav"
    with wave.open(str(audio), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"\0\0" * 16000)
    monkeypatch.setattr(media.shutil, "which", lambda _: "ffmpeg")
    monkeypatch.setattr(media.subprocess, "run", lambda *args, **kwargs: None)
    monkeypatch.setattr(media, "_probe_duration", lambda *args: 2.0)
    output = tmp_path / "final.mp4"
    media.render_video({"title": "Test", "scenes": [{"narration": "One two three", "visual": "Card", "duration_seconds": 60}]}, [audio], output, width=640, height=360)
    assert "00:00:00,000 --> 00:00:02,000" in output.with_suffix(".srt").read_text(encoding="utf-8")


def test_tts_chunk_cues_follow_measured_boundaries(tmp_path):
    audio = tmp_path / "voice.wav"
    audio.with_suffix(".timings.json").write_text(json.dumps([
        {"start": 0, "end": 0.75, "text": "First sentence."},
        {"start": 0.75, "end": 2, "text": "Second sentence."}]), encoding="utf-8")
    assert media._scene_cues(audio, "First sentence. Second sentence.", 2) == [
        (0.0, 0.75, "First sentence."), (0.75, 2.0, "Second sentence.")]


def test_long_cue_is_split_within_original_audio_bounds():
    cues = media._split_long_cues([(1.0, 5.0, "one two three four five six seven eight nine ten")])
    assert len(cues) == 2
    assert cues[0][0] == 1.0 and cues[-1][1] == 5.0
    assert cues[0][1] == cues[1][0]
    assert " ".join(cue[2] for cue in cues) == "one two three four five six seven eight nine ten"


def test_selectable_caption_keeps_actual_tts_chunk_boundaries(tmp_path):
    audio = tmp_path / "voice.wav"
    text = "one two three four five six seven eight nine ten"
    audio.with_suffix(".timings.json").write_text(json.dumps([{"start": 0, "end": 2, "text": text}]), encoding="utf-8")
    assert media._scene_cues(audio, text, 2, split_long=False) == [(0.0, 2.0, text)]
    assert len(media._scene_cues(audio, text, 2, split_long=True)) == 2


def test_subtitles_can_be_exported_without_burning_into_video(tmp_path, monkeypatch):
    audio = tmp_path / "voice.wav"
    with wave.open(str(audio), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"\0\0" * 16000)
    calls = []
    monkeypatch.setattr(media.shutil, "which", lambda _: "ffmpeg")
    monkeypatch.setattr(media.subprocess, "run", lambda args, **kwargs: calls.append(args))
    monkeypatch.setattr(media, "_probe_duration", lambda *args: 2.0)
    output = tmp_path / "video.mp4"
    media.render_video({"title": "Test", "scenes": [{"narration": "Test narration", "visual": "Card"}]},
                       [audio], output, width=360, height=640, burn_subtitles=False)
    assert "Test narration" in output.with_suffix(".srt").read_text(encoding="utf-8")
    assert "subtitles=" not in calls[0][calls[0].index("-vf") + 1]
    assert calls[0][calls[0].index("-t") + 1] == "2.000000"


def test_broll_is_labeled_and_uses_only_narration_audio(tmp_path, monkeypatch):
    from PIL import Image
    image = tmp_path / "card.png"
    Image.new("RGB", (360, 640)).save(image)
    stock = tmp_path / "stock.mp4"
    stock.write_bytes(b"video")
    audio = tmp_path / "voice.wav"
    with wave.open(str(audio), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"\0\0" * 16000)
    broll = {"path": str(stock), "creator": "Videographer", "rights_type": "licensed", "rights_verified": True,
             "license": "License", "attribution": "Videographer", "source_url": "https://example.com/clip",
             "rights_url": "https://example.com/license", "depiction": "illustrative"}
    asset = {"path": str(image), "creator": "Creator", "rights_type": "original", "rights_verified": True,
             "broll": broll}
    calls = []
    monkeypatch.setattr(media.shutil, "which", lambda _: "ffmpeg")
    monkeypatch.setattr(media.subprocess, "run", lambda args, **kwargs: calls.append(args))
    monkeypatch.setattr(media, "_probe_duration", lambda *args: 2.0)
    media.render_video({"title": "Test", "scenes": [{"narration": "Test", "asset": asset}]},
                       [audio], tmp_path / "final.mp4", width=360, height=640, burn_subtitles=False)
    assert "1:a:0" in calls[0] and "2:a:0" not in calls[0]
    assert (tmp_path / "render-scenes/001-stock-label-00.png").exists()
    asset["broll"] = [dict(broll, start_seconds=0), dict(broll, start_seconds=1)]
    with pytest.raises(ValueError, match="non-overlapping"):
        media.render_video({"title": "Test", "scenes": [{"narration": "Test", "asset": asset}]},
                           [audio], tmp_path / "second.mp4", width=360, height=640, burn_subtitles=False)


def test_video_quality_checks_duration_resolution_and_audio(tmp_path, monkeypatch):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"x" * 100000)
    monkeypatch.setattr(media.shutil, "which", lambda _: "ffprobe")
    def probe(duration, streams):
        monkeypatch.setattr(media.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=0, stdout=json.dumps({"format":{"duration":duration},"streams":streams})))
    probe(600, [{"codec_type":"video","width":1920,"height":1080,"avg_frame_rate":"30/1"},{"codec_type":"audio"}])
    assert media.validate_video(video) == []
    probe(1081, [{"codec_type":"video","width":1280,"height":720,"avg_frame_rate":"30/1"}])
    errors = media.validate_video(video)
    assert len(errors) == 3
    assert any("exceeds" in x for x in errors)
    assert any("resolution" in x for x in errors)
    assert any("audio" in x for x in errors)
