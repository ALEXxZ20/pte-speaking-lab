"""Delete one comparison and garbage-collect only files with no remaining revisions."""
import json
from pathlib import Path

from app.persistence.database import connect


def _candidate_assets(db, sample_ids: list[str]) -> tuple[set[str], set[str]]:
    audio_ids: set[str] = set()
    screenshot_ids: set[str] = set()
    for sample_id in sample_ids:
        for row in db.execute("SELECT payload_json FROM sample_revisions WHERE sample_id=?", (sample_id,)):
            payload = json.loads(row["payload_json"])
            if payload.get("audio_asset_id"):
                audio_ids.add(payload["audio_asset_id"])
            screenshot_ids.update(payload.get("color_screenshot_asset_ids", []))
    return audio_ids, screenshot_ids


def _other_assets(db, excluded: set[str]) -> tuple[set[str], set[str]]:
    audio_ids: set[str] = set()
    screenshot_ids: set[str] = set()
    for row in db.execute("SELECT sample_id,payload_json FROM sample_revisions"):
        if row["sample_id"] in excluded:
            continue
        payload = json.loads(row["payload_json"])
        if payload.get("audio_asset_id"):
            audio_ids.add(payload["audio_asset_id"])
        screenshot_ids.update(payload.get("color_screenshot_asset_ids", []))
    return audio_ids, screenshot_ids


def _selection(db, comparison_id: str) -> dict | None:
    row = db.execute("SELECT c.exercise_id,c.user_sample_id,c.benchmark_sample_id,e.reading_screenshot_asset_id FROM comparisons c JOIN exercises e ON e.id=c.exercise_id WHERE c.id=?", (comparison_id,)).fetchone()
    if not row:
        return None
    sample_ids = [row["user_sample_id"], row["benchmark_sample_id"]]
    run_ids = [item["id"] for item in db.execute("SELECT id FROM analysis_runs WHERE comparison_id=?", (comparison_id,))]
    audio, screenshots = _candidate_assets(db, sample_ids)
    if row["reading_screenshot_asset_id"]:
        screenshots.add(row["reading_screenshot_asset_id"])
    other_audio, other_screenshots = _other_assets(db, set(sample_ids))
    other_screenshots.update(item["reading_screenshot_asset_id"] for item in db.execute(
        "SELECT reading_screenshot_asset_id FROM exercises WHERE id<>? AND reading_screenshot_asset_id IS NOT NULL", (row["exercise_id"],)))
    return {"exercise_id": row["exercise_id"], "sample_ids": sample_ids, "run_ids": run_ids,
            "delete_audio_ids": sorted(audio - other_audio),
            "delete_screenshot_ids": sorted(screenshots - other_screenshots),
            "preserved_shared_assets": len(audio & other_audio) + len(screenshots & other_screenshots)}


def preview_deletion(path: Path, comparison_id: str) -> dict | None:
    with connect(path) as db:
        selection = _selection(db, comparison_id)
        if not selection:
            return None
        audio_files = [row["relative_path"] for asset_id in selection["delete_audio_ids"]
                       if (row := db.execute("SELECT relative_path FROM audio_assets WHERE id=?", (asset_id,)).fetchone())]
        screenshot_files = [row["relative_path"] for asset_id in selection["delete_screenshot_ids"]
                            if (row := db.execute("SELECT relative_path FROM screenshot_assets WHERE id=?", (asset_id,)).fetchone())]
        return {"comparison_id": comparison_id, "sample_count": len(selection["sample_ids"]),
                "run_count": len(selection["run_ids"]), "audio_file_count": len(selection["delete_audio_ids"]),
                "screenshot_file_count": len(selection["delete_screenshot_ids"]),
                "files": audio_files + screenshot_files,
                "preserved_shared_assets": selection["preserved_shared_assets"]}


def delete_comparison(path: Path, data_dir: Path, comparison_id: str) -> dict | None:
    files: list[str] = []
    with connect(path) as db:
        db.execute("BEGIN IMMEDIATE")
        selection = _selection(db, comparison_id)
        if not selection:
            return None
        for run_id in selection["run_ids"]:
            db.execute("DELETE FROM finding_evidence WHERE finding_id IN (SELECT id FROM findings WHERE run_id=?)", (run_id,))
            for table in ("findings", "evidence", "metrics", "timed_tokens", "comparisons_result"):
                db.execute(f"DELETE FROM {table} WHERE run_id=?", (run_id,))
            db.execute("DELETE FROM analysis_runs WHERE id=?", (run_id,))
        db.execute("DELETE FROM comparisons WHERE id=?", (comparison_id,))
        for sample_id in selection["sample_ids"]:
            for table in ("screenshot_imports", "sample_screenshots", "pause_labels", "sample_tokens", "external_scores", "sample_revisions"):
                db.execute(f"DELETE FROM {table} WHERE sample_id=?", (sample_id,))
            db.execute("DELETE FROM response_samples WHERE id=?", (sample_id,))
        db.execute("DELETE FROM exercises WHERE id=?", (selection["exercise_id"],))
        for asset_id in selection["delete_audio_ids"]:
            row = db.execute("SELECT relative_path FROM audio_assets WHERE id=?", (asset_id,)).fetchone()
            if row:
                files.extend([row["relative_path"], f"audio/derived/{asset_id}.16k.wav"])
                db.execute("DELETE FROM audio_assets WHERE id=?", (asset_id,))
        for asset_id in selection["delete_screenshot_ids"]:
            row = db.execute("SELECT relative_path FROM screenshot_assets WHERE id=?", (asset_id,)).fetchone()
            if row:
                files.append(row["relative_path"])
                db.execute("DELETE FROM screenshot_assets WHERE id=?", (asset_id,))
    # The database transaction commits before file removal. A failed unlink leaves an
    # unreferenced local file, which can be cleaned later without losing live data.
    failed: list[str] = []
    removed = 0
    for relative in files:
        try:
            file = data_dir / relative
            if file.exists():
                file.unlink()
                removed += 1
        except OSError:
            failed.append(relative)
    return {"comparison_id": comparison_id, "deleted": True, "files_removed": removed,
            "file_cleanup_pending": failed}
