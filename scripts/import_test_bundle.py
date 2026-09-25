#!/usr/bin/env python3
"""Import the user's private same-question bundle into ignored local data, without confirming colors."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--analyze", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    marker = settings.data_dir / "test_bundle_import.json"
    if marker.exists():
        print(marker.read_text())
        return
    samples = []
    with TestClient(create_app(settings)) as client:
        for role, folder, scores in (("user", "用户数据", (71, 74, 5)),
                                     ("benchmark", "高分数据", (77, 81, 4.9))):
            base = ROOT / "测试数据包" / folder
            audio = next(base.glob("*.m4a"))
            screenshot = next(base.glob("*逐词颜色*"))
            with audio.open("rb") as source:
                audio_result = client.post("/api/v1/assets/audio", files={"file": (audio.name, source, "audio/mp4")})
            with screenshot.open("rb") as source:
                screenshot_result = client.post("/api/v1/assets/screenshots", files={"file": (screenshot.name, source, "image/png")})
            audio_result.raise_for_status(); screenshot_result.raise_for_status()
            samples.append({"role": role, "audio_asset_id": audio_result.json()["id"],
                            "color_screenshot_asset_ids": [screenshot_result.json()["id"]],
                            "transcript_raw": (base / "content.txt").read_text(encoding="utf-8"),
                            "transcript_source": "xingji_copy",
                            "pronunciation_score": {"value": scores[0], "max": 90},
                            "fluency_score": {"value": scores[1], "max": 90},
                            "content_score": {"value": scores[2], "max": 5}})
        response = client.post("/api/v1/comparisons", json={"exercise": {"question_type": "DI", "title": "真实双边测试数据包"}, "samples": samples})
        response.raise_for_status()
        comparison = response.json()
        mapped = {}
        for sample in samples:
            role = sample["role"]
            result = client.post(f"/api/v1/samples/{comparison['samples'][role]['id']}/screenshot-imports",
                                 json={"screenshot_id": sample["color_screenshot_asset_ids"][0]})
            result.raise_for_status()
            mapped[role] = result.json()["draft"]["candidate_count"]
        run_id = None
        if args.analyze:
            run = client.post(f"/api/v1/comparisons/{comparison['id']}/runs", json={})
            run.raise_for_status()
            run_id = run.json()["run_id"]
    summary = {"comparison_id": comparison["id"], "run_id": run_id,
               "candidate_counts": mapped, "colors_confirmed": False}
    marker.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
