import json
from types import SimpleNamespace
from woori_youtube import media


def test_video_quality_checks_duration_resolution_and_audio(tmp_path, monkeypatch):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"x" * 100000)
    monkeypatch.setattr(media.shutil, "which", lambda _: "ffprobe")
    def probe(duration, streams):
        monkeypatch.setattr(media.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=0, stdout=json.dumps({"format":{"duration":duration},"streams":streams})))
    probe(600, [{"codec_type":"video","width":1920,"height":1080},{"codec_type":"audio"}])
    assert media.validate_video(video) == []
    probe(1081, [{"codec_type":"video","width":1280,"height":720}])
    errors = media.validate_video(video)
    assert len(errors) == 3
    assert any("exceeds" in x for x in errors)
    assert any("resolution" in x for x in errors)
    assert any("audio" in x for x in errors)
