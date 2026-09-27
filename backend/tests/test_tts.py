"""验证 TTS 的时间基准、缓存和证据边界；测试不访问在线服务。"""
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.audio.alignment import tts_word_boundaries
from app.config import Settings
from app.engines.fluency import analyze_fluency
from app.main import create_app
from app.persistence.database import migrate
from app.providers import edge_tts
from app.screenshots.mapper import tokenize


def test_segment_preview_respects_sentence_boundaries():
    text = "We are talking about lunch today. The cafeteria has good food.\nFinally, students leave."
    assert edge_tts.preview_segments(text) == ["We are talking about lunch today.",
                                              "The cafeteria has good food.", "Finally, students leave."]


def test_synthetic_gap_offsets_words_and_is_not_counted_as_pause(tmp_path: Path, monkeypatch):
    settings = Settings(pte_data_dir=tmp_path, tts_gap_ms=300)
    migrate(settings.database_path)

    async def fake_request(text, voice, rate, timeout):
        return b"test", [{"text": text, "start_s": 0.1, "end_s": 0.2}]

    monkeypatch.setattr(edge_tts, "_request_segment", fake_request)
    monkeypatch.setattr(edge_tts, "_decode_mp3", lambda audio, config: np.full(12000, 8000, dtype="<i2"))
    result = edge_tts.generate(["Hello", "today"], edge_tts.VOICES[0], "+0%", settings)
    assert result["seam_intervals"] == [{"start_s": 0.5, "end_s": 0.8, "boundary_s": 0.5, "kind": "tts_segment_boundary"}]
    alignment = tts_word_boundaries(tokenize(result["text"]), result["word_boundaries"], 1.3)
    assert [item["start_s"] for item in alignment["tokens"]] == [0.1, 0.9]
    assert edge_tts.generate(["Hello", "today"], edge_tts.VOICES[0], "+0%", settings)["cached"]

    sample = {"tokens": tokenize(result["text"]), "fluency_score": None}
    audio = {"speech_regions": {"quality": "medium", "speech_s": 0.8,
                                "regions": [{"start_s": 0.05, "end_s": 0.45}, {"start_s": 0.85, "end_s": 1.25}]},
             "tts": {"seam_intervals": result["seam_intervals"]}}
    fluency = analyze_fluency("sample_test", sample, audio, alignment)
    assert fluency["metrics"]["pause_count"]["value"] == 0


def test_tts_boundary_mismatch_remains_untrusted():
    tokens = tokenize("I have 15 minutes")
    events = [{"text": value, "start_s": i * 0.3, "end_s": i * 0.3 + 0.2}
              for i, value in enumerate(["I", "have", "fifteen", "minutes"])]
    result = tts_word_boundaries(tokens, events, 3)
    assert result["status"] == "partial"
    assert result["tokens"][2]["start_s"] is None


def test_generation_rejects_unapproved_voice(tmp_path: Path):
    settings = Settings(pte_data_dir=tmp_path)
    migrate(settings.database_path)
    with pytest.raises(ValueError, match="tts_voice_or_rate_invalid"):
        edge_tts.generate(["Hello"], "unknown", "+0%", settings)


def test_tts_api_history_and_immutable_report(tmp_path: Path, monkeypatch):
    """TTS 参考没有猩际分数；重跑与历史记录仍使用既有比较合同。"""
    settings = Settings(_env_file=None, pte_data_dir=tmp_path, alignment_provider="none")

    async def fake_request(text, voice, rate, timeout):
        return b"audio", [{"text": "Hello", "start_s": 0.1, "end_s": 0.35}]

    monkeypatch.setattr(edge_tts, "_request_segment", fake_request)
    monkeypatch.setattr(edge_tts, "_decode_mp3", lambda audio, config: np.full(24000, 8000, dtype="<i2"))
    with TestClient(create_app(settings)) as client:
        generated = client.post("/api/v1/tts/generations", json={"segments": ["Hello"]})
        assert generated.status_code == 200, generated.text
        asset_id = generated.json()["audio_asset_id"]
        assert client.post("/api/v1/tts/generations", json={"segments": ["Hello"]}).json()["cached"]
        sides = [
            {"role": "user", "audio_asset_id": asset_id, "transcript_raw": "Hello"},
            {"role": "benchmark", "audio_origin": "edge_tts", "audio_asset_id": asset_id,
             "transcript_raw": "Hello", "transcript_source": "tts_script"},
        ]
        created = client.post("/api/v1/comparisons", json={"exercise": {"question_type": "DI", "reading_text_raw": "Hello"}, "samples": sides})
        assert created.status_code == 200, created.text
        comparison_id = created.json()["id"]
        history = client.get("/api/v1/history").json()
        assert history[0]["comparison_mode"] == "tts"
        run = client.post(f"/api/v1/comparisons/{comparison_id}/runs", json={})
        assert run.status_code == 200, run.text
        report = client.get(f"/api/v1/runs/{run.json()['run_id']}/report").json()
        assert report["samples"]["benchmark"]["sample"]["pronunciation_score"] is None
        assert report["samples"]["benchmark"]["alignment"]["trusted_count"] == 1
        assert report["comparison"]["reference_kind"] == "tts"
        assert client.post(f"/api/v1/comparisons/{comparison_id}/runs", json={}).status_code == 200
        assert client.get(f"/api/v1/runs/{run.json()['run_id']}/report").json() == report
