"""Check display extraction against known signal and its independent failure path."""
import math
import subprocess
import wave

from app.audio.acoustics import extract, extract_bounded


def _wav(path, values):
    import numpy as np
    with wave.open(str(path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(16000)
        target.writeframes(np.asarray(values, dtype="<i2").tobytes())


def test_pitch_energy_curve_tracks_tone_and_silence_without_scoring(tmp_path):
    import numpy as np
    sample_rate = 16000
    tone = [int(12000 * math.sin(2 * math.pi * 200 * index / sample_rate)) for index in range(sample_rate)]
    path = tmp_path / "tone.wav"
    _wav(path, [0] * (sample_rate // 2) + tone)
    result = extract(path)
    assert result["status"] == "complete"
    assert all(point["pitch_hz"] is None for point in result["points"][:6])
    pitches = [point["pitch_hz"] for point in result["points"] if point["pitch_hz"] is not None]
    assert np.median(pitches) == np.median(pitches) and 190 < np.median(pitches) < 210
    assert result["points"][0]["energy_dbfs"] < result["points"][-1]["energy_dbfs"]
    assert "score" not in result


def test_silence_and_timeout_do_not_raise(tmp_path, monkeypatch):
    path = tmp_path / "silence.wav"
    _wav(path, [0] * 16000)
    assert extract(path)["reason"] == "no_audible_signal"

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="acoustics", timeout=1)

    monkeypatch.setattr(subprocess, "run", timeout)
    assert extract_bounded(path, timeout_s=1)["reason"] == "processing_timeout"
