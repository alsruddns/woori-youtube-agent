import json
import wave
import numpy as np

from woori_youtube.audio_brand import make_original_bed
from woori_youtube.content_types import ContentType


def test_generated_bed_is_non_silent_and_records_provenance(tmp_path):
    path = make_original_bed(tmp_path / "bed.wav", ContentType.SINGLE_SHORT)
    with wave.open(str(path), "rb") as wav:
        assert wav.getframerate() == 48000 and wav.getnchannels() == 1
        samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2")
    assert np.max(np.abs(samples.astype(np.int32))) > 500
    assert np.max(np.abs(samples.astype(np.int32))) < 12000
    provenance = json.loads(path.with_suffix(".license.json").read_text(encoding="utf-8"))
    assert provenance["external_samples"] is False and provenance["bpm"] == 132
