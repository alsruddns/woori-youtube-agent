import json
import wave
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
