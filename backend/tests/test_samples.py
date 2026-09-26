import io
import json
import wave

from fastapi.testclient import TestClient
from PIL import Image

from app.config import Settings
from app.main import create_app
from app.persistence.database import connect


def wav_bytes():
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\0\0" * 16000)
    return output.getvalue()


def test_assets_dual_sample_and_immutable_revisions(tmp_path):
    settings = Settings(_env_file=None, pte_data_dir=tmp_path)
    with TestClient(create_app(settings)) as client:
        original = wav_bytes()
        upload = client.post("/api/v1/assets/audio", files={"file": ("example.m4a", original, "audio/mp4")})
        assert upload.status_code == 200, upload.text
        audio_id = upload.json()["id"]
        assert client.get(f"/api/v1/assets/audio/{audio_id}").content == original
        picture = io.BytesIO()
        Image.new("RGB", (20, 20), "green").save(picture, format="PNG")
        screenshot = client.post("/api/v1/assets/screenshots", files={"file": ("sample.png", picture.getvalue(), "image/png")})
        assert screenshot.status_code == 200, screenshot.text
        screenshot_id = screenshot.json()["id"]
        samples = [
            {"role": role, "audio_asset_id": audio_id, "transcript_raw": "One two.",
             "transcript_source": "xingji_copy", "color_screenshot_asset_ids": [screenshot_id],
             "pronunciation_score": {"value": 70, "max": 90},
             "fluency_score": {"value": 80, "max": 90},
             "content_score": {"value": 5, "max": 5}}
            for role in ("user", "benchmark")
        ]
        samples[0]["audio_origin"] = "human_recording"
        samples[1]["audio_origin"] = "ai_generated"
        created = client.post("/api/v1/comparisons", json={"exercise": {"question_type": "DI", "reading_text_raw": "One two."}, "samples": samples})
        assert created.status_code == 200, created.text
        comparison = created.json()
        assert comparison["exercise"]["reading_text_raw"] == "One two."
        assert comparison["samples"]["benchmark"]["sample"]["audio_origin"] == "ai_generated"
        assert set(comparison["samples"]) == {"user", "benchmark"}
        assert len(client.get("/api/v1/history").json()) == 1
        user = comparison["samples"]["user"]
        edited = user["sample"]
        edited["tokens"][0].update(color="red", color_review_status="confirmed", color_source_screenshot_id=screenshot_id)
        result = client.patch(f"/api/v1/samples/{user['id']}", json={"expected_version": 1, "sample": edited})
        assert result.status_code == 200, result.text
        assert result.json()["version"] == 2
        assert client.patch(f"/api/v1/samples/{user['id']}", json={"expected_version": 1, "sample": edited}).status_code == 409
        with connect(settings.database_path) as db:
            revisions = db.execute("SELECT version,payload_json FROM sample_revisions WHERE sample_id=? ORDER BY version", (user["id"],)).fetchall()
            assert [row["version"] for row in revisions] == [1, 2]
            assert json.loads(revisions[0]["payload_json"])["tokens"][0]["color"] == "unknown"
            assert json.loads(revisions[1]["payload_json"])["tokens"][0]["color"] == "red"
            assert db.execute("SELECT value FROM external_scores WHERE sample_id=? AND dimension='content'", (user["id"],)).fetchone()[0] == 5


def test_unconfirmed_color_cannot_be_saved(tmp_path):
    with TestClient(create_app(Settings(_env_file=None, pte_data_dir=tmp_path))) as client:
        body = {"exercise": {"question_type": "DI"}, "samples": [
            {"role": "user", "transcript_raw": "Hello", "tokens": [{"index": 0, "surface": "Hello", "color": "red"}]},
            {"role": "benchmark", "transcript_raw": "Hello"}]}
        response = client.post("/api/v1/comparisons", json=body)
        assert response.status_code == 422


def test_deleting_comparison_preserves_shared_assets(tmp_path):
    settings = Settings(_env_file=None, pte_data_dir=tmp_path)
    with TestClient(create_app(settings)) as client:
        original = wav_bytes()
        audio_id = client.post("/api/v1/assets/audio", files={"file": ("sample.wav", original, "audio/wav")}).json()["id"]
        picture = io.BytesIO()
        Image.new("RGB", (20, 20), "green").save(picture, format="PNG")
        screenshot_id = client.post("/api/v1/assets/screenshots", files={"file": ("sample.jpg", picture.getvalue(), "image/jpeg")}).json()["id"]
        body = {"exercise": {"question_type": "DI"}, "samples": [
            {"role": role, "audio_asset_id": audio_id, "transcript_raw": "Hello there",
             "color_screenshot_asset_ids": [screenshot_id]} for role in ("user", "benchmark")
        ]}
        first = client.post("/api/v1/comparisons", json=body).json()["id"]
        second = client.post("/api/v1/comparisons", json=body).json()["id"]
        preview = client.get(f"/api/v1/comparisons/{first}/deletion-preview").json()
        assert preview["audio_file_count"] == 0 and preview["screenshot_file_count"] == 0
        assert client.delete(f"/api/v1/comparisons/{first}").json()["deleted"]
        assert client.get(f"/api/v1/assets/audio/{audio_id}").content == original
        assert client.get(f"/api/v1/assets/screenshots/{screenshot_id}").status_code == 200
        preview = client.get(f"/api/v1/comparisons/{second}/deletion-preview").json()
        assert preview["audio_file_count"] == 1 and preview["screenshot_file_count"] == 1
        assert client.delete(f"/api/v1/comparisons/{second}").json()["files_removed"] == 2
        assert client.get(f"/api/v1/assets/audio/{audio_id}").status_code == 404
        assert client.get(f"/api/v1/assets/screenshots/{screenshot_id}").status_code == 404
