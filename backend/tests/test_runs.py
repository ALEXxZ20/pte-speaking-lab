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


def test_cloud_request_without_key_keeps_local_summaries_and_hides_key(tmp_path):
    settings = Settings(_env_file=None, pte_data_dir=tmp_path, alignment_provider="none")
    with TestClient(create_app(settings)) as client:
        audio = client.post("/api/v1/assets/audio", files={"file": ("sample.wav", one_second_silence(), "audio/wav")}).json()
        sides = [{"role": role, "audio_asset_id": audio["id"], "transcript_raw": "Hello there"}
                 for role in ("user", "benchmark")]
        comparison = client.post("/api/v1/comparisons", json={"exercise": {"question_type": "DI"}, "samples": sides}).json()
        result = client.post(f"/api/v1/comparisons/{comparison['id']}/runs", json={"allow_cloud": True})
        assert result.status_code == 200
        report = client.get(f"/api/v1/runs/{result.json()['run_id']}/report").json()
        assert report["config"]["llm_requested"] is True
        assert report["config"]["llm_provider"] == "none"
        assert report["summaries"]["fluency"]["source"] == "local_rules"
        assert report["summaries"]["practice"]["source"] == "local_rules"
        assert "openai_api_key" not in client.get("/api/v1/settings/providers").text


def test_compatible_provider_can_rewrite_findings_without_exposing_key(tmp_path, monkeypatch):
    from app.providers.openai_llm import OpenAICompatibleLLMProvider

    calls = []
    def rewrite(self, findings, evidence):
        calls.append((self.base_url, self.model, len(evidence)))
        return [{"id": finding["id"], "evidence_ids": finding["evidence_ids"],
                 "statement": finding["statement"], "recommendation": "请回听并重录。"} for finding in findings]

    monkeypatch.setattr(OpenAICompatibleLLMProvider, "explain", rewrite)
    def summarize(self, metrics, findings, practice_facts, fluency_baseline, practice_baseline):
        return {"fluency": {"text": "请先回听停顿候选，再判断是否需要调整节奏。", "metric_keys": list(metrics)},
                "practice": {"text": "请回听 Hello 所在短句，再重录比较。", "finding_ids": [item["id"] for item in findings]}}
    monkeypatch.setattr(OpenAICompatibleLLMProvider, "summarize_report", summarize)
    settings = Settings(_env_file=None, pte_data_dir=tmp_path, alignment_provider="none",
                        llm_provider="openai_compatible", openai_api_key="test-local-key",
                        openai_analysis_model="gpt-6-sol", openai_base_url="http://localhost:8317/")
    with TestClient(create_app(settings)) as client:
        audio = client.post("/api/v1/assets/audio", files={"file": ("sample.wav", one_second_silence(), "audio/wav")}).json()
        sides = [{"role": role, "audio_asset_id": audio["id"], "transcript_raw": "Hello there",
                  "tokens": [{"index": 0, "surface": "Hello", "color": "red" if role == "user" else "green",
                              "color_review_status": "confirmed"}, {"index": 1, "surface": "there"}]}
                 for role in ("user", "benchmark")]
        comparison = client.post("/api/v1/comparisons", json={"exercise": {"question_type": "DI"}, "samples": sides}).json()
        response = client.post(f"/api/v1/comparisons/{comparison['id']}/runs", json={"allow_cloud": True})
        assert response.status_code == 200, response.text
        report = client.get(f"/api/v1/runs/{response.json()['run_id']}/report").json()
        assert report["diagnosis"]["llm_status"] == "used"
        assert report["summaries"]["fluency"]["source"] == "ai"
        assert report["config"]["llm_provider"] == "openai_compatible"
        assert calls == [("http://localhost:8317/v1", "gpt-6-sol", 1)]
        assert "test-local-key" not in client.get("/api/v1/settings/providers").text
        assert "test-local-key" not in client.get(f"/api/v1/runs/{response.json()['run_id']}/report").text


def test_screenshot_candidate_colors_enter_first_run_with_lower_quality(tmp_path):
    settings = Settings(_env_file=None, pte_data_dir=tmp_path, alignment_provider="none")
    with TestClient(create_app(settings)) as client:
        audio = client.post("/api/v1/assets/audio", files={"file": ("sample.wav", one_second_silence(), "audio/wav")}).json()
        from PIL import Image
        import io
        picture = io.BytesIO()
        Image.new("RGB", (20, 20), "red").save(picture, format="PNG")
        screenshot = client.post("/api/v1/assets/screenshots", files={"file": ("words.png", picture.getvalue(), "image/png")}).json()
        sides = [{"role": role, "audio_asset_id": audio["id"], "color_screenshot_asset_ids": [screenshot["id"]],
                  "transcript_raw": "Hello there", "transcript_source": "screenshot_ocr", "ocr_transcript_raw": "Hello there",
                  "tokens": [{"index": 0, "surface": "Hello", "color": "red" if role == "user" else "green",
                              "color_review_status": "candidate", "color_source_screenshot_id": screenshot["id"]},
                             {"index": 1, "surface": "there"}]}
                 for role in ("user", "benchmark")]
        comparison = client.post("/api/v1/comparisons", json={"exercise": {"question_type": "DI",
            "reading_text_raw": "Hello there", "reading_text_source": "screenshot_ocr",
            "reading_text_ocr_raw": "Hello there", "reading_screenshot_asset_id": screenshot["id"]}, "samples": sides})
        assert comparison.status_code == 200, comparison.text
        run = client.post(f"/api/v1/comparisons/{comparison.json()['id']}/runs", json={})
        assert run.status_code == 200, run.text
        report = client.get(f"/api/v1/runs/{run.json()['run_id']}/report").json()
        assert report["samples"]["user"]["pronunciation"]["summary"]["candidate_count"] == 1
        assert report["samples"]["user"]["pronunciation"]["summary"]["unknown_count"] == 1
        assert report["samples"]["user"]["pronunciation"]["evidence"][0]["quality"] == "low"
        assert report["comparison"]["shared_word_pairs"][0]["user_color"] == "red"
        assert report["diagnosis"]["findings"][0]["confidence_level"] == "low"
        user = comparison.json()["samples"]["user"]
        edited = user["sample"]
        edited["tokens"][0]["color_review_status"] = "confirmed"
        assert client.patch(f"/api/v1/samples/{user['id']}", json={"expected_version": 1, "sample": edited}).status_code == 200
        old = client.get(f"/api/v1/runs/{run.json()['run_id']}/report").json()
        assert old["samples"]["user"]["sample"]["tokens"][0]["color_review_status"] == "candidate"


def test_openpronounce_availability_is_reported_without_starting_model(tmp_path, monkeypatch):
    import app.api.runs as runs_api

    original = runs_api.importlib.util.find_spec
    with TestClient(create_app(Settings(_env_file=None, pte_data_dir=tmp_path))) as client:
        monkeypatch.setattr(runs_api.importlib.util, "find_spec", lambda name: None if name == "openpronounce" else original(name))
        assert client.get("/api/v1/settings/providers").json()["openpronounce_available"] is False
        monkeypatch.setattr(runs_api.importlib.util, "find_spec", lambda name: object() if name == "openpronounce" else original(name))
        assert client.get("/api/v1/settings/providers").json()["openpronounce_available"] is True
