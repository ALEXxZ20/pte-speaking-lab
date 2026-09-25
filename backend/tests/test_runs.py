from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from test_audio import one_second_silence


def test_run_survives_input_revision_and_degrades_without_alignment(tmp_path):
    settings = Settings(_env_file=None, pte_data_dir=tmp_path, alignment_provider="none")
    with TestClient(create_app(settings)) as client:
        audio = client.post("/api/v1/assets/audio", files={"file": ("sample.wav", one_second_silence(), "audio/wav")}).json()
        sides = [{"role": role, "audio_asset_id": audio["id"], "transcript_raw": "Hello there", "transcript_source": "xingji_copy",
                  "content_score": {"value": 5, "max": 5}} for role in ("user", "benchmark")]
        comparison = client.post("/api/v1/comparisons", json={"exercise": {"question_type": "DI"}, "samples": sides}).json()
        run = client.post(f"/api/v1/comparisons/{comparison['id']}/runs", json={})
        assert run.status_code == 200, run.text
        assert run.json()["status"] == "partial"
        report = client.get(f"/api/v1/runs/{run.json()['run_id']}/report").json()
        assert report["samples"]["user"]["fluency"]["metrics"]["wpm"]["value"] is None
        assert report["samples"]["user"]["sample"]["content_score"]["value"] == 5
        user = comparison["samples"]["user"]
        updated = user["sample"]
        updated["content_score"] = {"value": 4, "max": 5}
        response = client.patch(f"/api/v1/samples/{user['id']}", json={"expected_version": 1, "sample": updated})
        assert response.status_code == 200
        assert client.get(f"/api/v1/runs/{run.json()['run_id']}/report").json()["samples"]["user"]["sample"]["content_score"]["value"] == 5
        assert client.get(f"/api/v1/comparisons/{comparison['id']}").json()["samples"]["user"]["sample"]["content_score"]["value"] == 4


def test_confirmed_colors_produce_traceable_pronunciation_findings(tmp_path):
    settings = Settings(_env_file=None, pte_data_dir=tmp_path, alignment_provider="none")
    with TestClient(create_app(settings)) as client:
        audio = client.post("/api/v1/assets/audio", files={"file": ("sample.wav", one_second_silence(), "audio/wav")}).json()
        sides = [
            {"role": role, "audio_asset_id": audio["id"], "transcript_raw": "Hello there",
             "transcript_source": "xingji_copy", "tokens": [
                 {"index": 0, "surface": "Hello", "color": "red" if role == "user" else "green",
                  "color_review_status": "confirmed"},
                 {"index": 1, "surface": "there", "color": "yellow" if role == "user" else "green",
                  "color_review_status": "confirmed"},
             ]} for role in ("user", "benchmark")
        ]
        comparison = client.post("/api/v1/comparisons", json={"exercise": {"question_type": "DI"}, "samples": sides})
        assert comparison.status_code == 200, comparison.text
        run = client.post(f"/api/v1/comparisons/{comparison.json()['id']}/runs", json={})
        assert run.status_code == 200, run.text
        report = client.get(f"/api/v1/runs/{run.json()['run_id']}/report").json()
        assert report["samples"]["user"]["pronunciation"]["summary"]["counts"]["red"] == 1
        assert report["samples"]["benchmark"]["pronunciation"]["summary"]["counts"]["green"] == 2
        assert report["diagnosis"]["findings"][0]["kind"] == "red_word_practice"
        evidence = {item["id"] for item in report["samples"]["user"]["pronunciation"]["evidence"]}
        assert set(report["diagnosis"]["findings"][0]["evidence_ids"]) <= evidence
        assert all(item["start_s"] is None for item in report["samples"]["user"]["pronunciation"]["targets"])
        assert report["comparison"]["shared_word_pairs"][0]["user_color"] == "red"


def test_cloud_requires_explicit_key_and_model_without_leaking_key(tmp_path):
    settings = Settings(_env_file=None, pte_data_dir=tmp_path, alignment_provider="none")
    with TestClient(create_app(settings)) as client:
        audio = client.post("/api/v1/assets/audio", files={"file": ("sample.wav", one_second_silence(), "audio/wav")}).json()
        sides = [{"role": role, "audio_asset_id": audio["id"], "transcript_raw": "Hello there"}
                 for role in ("user", "benchmark")]
        comparison = client.post("/api/v1/comparisons", json={"exercise": {"question_type": "DI"}, "samples": sides}).json()
        result = client.post(f"/api/v1/comparisons/{comparison['id']}/runs", json={"allow_cloud": True})
        assert result.status_code == 422
        assert result.json()["detail"]["code"] == "openai_key_and_model_required"
        assert client.get(f"/api/v1/comparisons/{comparison['id']}/runs").json() == []
        assert "openai_api_key" not in client.get("/api/v1/settings/providers").text
