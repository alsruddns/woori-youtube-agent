import json
import wave

import pytest

from woori_youtube import event_production


def test_render_blocks_on_actual_short_audio_before_render(tmp_path, monkeypatch):
    monkeypatch.setattr(event_production, "validate_event_script", lambda *_: [])
    monkeypatch.setattr(event_production, "validate_scene_assets", lambda *_: [])
    def synthesize(scenes, directory):
        directory.mkdir(parents=True)
        path = directory / "scene-001.wav"
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(8000)
            wav.writeframes(b"\0\0" * 16000)
        return [path]
    monkeypatch.setattr(event_production, "synthesize_scenes", synthesize)
    output = tmp_path / "output"
    with pytest.raises(event_production.ProductionBlocked, match="Actual narration is 2.0s"):
        event_production.render_event({}, {"scenes": [{"narration": "test"}]}, [{}], output, ffmpeg="ffmpeg")
    assert json.loads((output / "production.json").read_text())["narration_seconds"] == 2.0
    assert not (output / "final.mp4").exists()
    with pytest.raises(event_production.ProductionBlocked, match="not empty"):
        event_production.render_event({}, {"scenes": [{"narration": "test"}]}, [{}], output, ffmpeg="ffmpeg")
