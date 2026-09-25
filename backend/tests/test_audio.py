import hashlib
import io
import wave

import pytest
from fastapi.testclient import TestClient

from app.audio.alignment import NoAlignment
from app.audio.prepare import prepare_audio, speech_regions
from app.config import Settings
from app.main import create_app
from app.persistence.database import connect


def one_second_silence():
    memory = io.BytesIO()
    with wave.open(memory, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\0\0" * 16000)
    return memory.getvalue()


def test_prepare_preserves_original_and_no_alignment_does_not_guess(tmp_path):
    settings = Settings(_env_file=None, pte_data_dir=tmp_path)
    source = one_second_silence()
    with TestClient(create_app(settings)) as client:
        asset = client.post("/api/v1/assets/audio", files={"file": ("not-really-m4a.m4a", source, "audio/mp4")}).json()
    prepared = prepare_audio(asset["id"], settings)
    assert prepared["original_sha256"] == hashlib.sha256(source).hexdigest()
    assert prepared["speech_regions"]["quality"] == "low"
    assert prepared["speech_regions"]["regions"] == []
    wav_path = settings.data_dir / prepared["wav_path"]
    assert wav_path.exists()
    result = NoAlignment().align(wav_path, [{"index": 0, "surface": "hello"}], 1.0)
    assert result["tokens"][0]["start_s"] is None
    with connect(settings.database_path) as db:
        original = settings.data_dir / db.execute("SELECT relative_path FROM audio_assets WHERE id=?", (asset["id"],)).fetchone()[0]
    original.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="original_audio_hash_mismatch"):
        prepare_audio(asset["id"], settings)
