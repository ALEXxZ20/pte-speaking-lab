"""Transactional editable views and immutable sample snapshots."""
import json
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

from app.domain.schemas import ComparisonInput, SampleInput
from app.persistence.database import connect


def uid(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _assert_assets(db: sqlite3.Connection, sample: SampleInput) -> None:
    if sample.audio_asset_id and not db.execute("SELECT 1 FROM audio_assets WHERE id=?", (sample.audio_asset_id,)).fetchone():
        raise ValueError("audio_asset_not_found")
    for screenshot_id in sample.color_screenshot_asset_ids:
        if not db.execute("SELECT 1 FROM screenshot_assets WHERE id=?", (screenshot_id,)).fetchone():
            raise ValueError("screenshot_asset_not_found")
    for token in sample.tokens:
        if token.color_source_screenshot_id and token.color_source_screenshot_id not in sample.color_screenshot_asset_ids:
            raise ValueError("color_source_not_attached")


def _write_view(db: sqlite3.Connection, sample_id: str, sample: SampleInput, version: int) -> str:
    payload = sample.model_dump(mode="json")
    db.execute("UPDATE response_samples SET audio_asset_id=?, transcript_raw=?, transcript_source=?, input_payload_json=?, input_version=? WHERE id=?",
               (sample.audio_asset_id, sample.transcript_raw, sample.transcript_source, json.dumps(payload), version, sample_id))
    db.execute("DELETE FROM external_scores WHERE sample_id=?", (sample_id,))
    for dimension in ("pronunciation", "fluency", "content"):
        score = getattr(sample, f"{dimension}_score")
        if score:
            db.execute("INSERT INTO external_scores VALUES (?,?,?,?,?)", (sample_id, dimension, score.value, score.max, "xingji"))
    db.execute("DELETE FROM sample_tokens WHERE sample_id=?", (sample_id,))
    for token in sample.tokens:
        db.execute("INSERT INTO sample_tokens VALUES (?,?,?,?,?,?,?)", (sample_id, token.index, token.surface, token.normalized,
                   token.color, token.color_review_status, token.color_source_screenshot_id))
    db.execute("DELETE FROM pause_labels WHERE sample_id=?", (sample_id,))
    for pause in sample.pause_labels:
        db.execute("INSERT INTO pause_labels VALUES (?,?,?,?,?)", (uid("pause"), sample_id, pause.after_token_index, pause.raw_label, pause.review_status))
    db.execute("DELETE FROM sample_screenshots WHERE sample_id=?", (sample_id,))
    for order, screenshot_id in enumerate(sample.color_screenshot_asset_ids):
        db.execute("INSERT INTO sample_screenshots VALUES (?,?,?)", (sample_id, screenshot_id, order))
    revision_id = uid("revision")
    db.execute("INSERT INTO sample_revisions VALUES (?,?,?,?,?)", (revision_id, sample_id, version, json.dumps(payload), now()))
    return revision_id


def create_comparison(path, input_data: ComparisonInput) -> dict:
    exercise_id, comparison_id = uid("exercise"), uid("comparison")
    with connect(path) as db:
        for sample in input_data.samples:
            _assert_assets(db, sample)
        exercise = input_data.exercise
        if exercise.reading_screenshot_asset_id and not db.execute("SELECT 1 FROM screenshot_assets WHERE id=?", (exercise.reading_screenshot_asset_id,)).fetchone():
            raise ValueError("reading_screenshot_asset_not_found")
        db.execute("INSERT INTO exercises (id,question_type,title,source_note,source_question_id,reading_text_raw,reading_text_source,reading_text_ocr_raw,reading_screenshot_asset_id,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                   (exercise_id, exercise.question_type, exercise.title, exercise.source_note, exercise.source_question_id, exercise.reading_text_raw, exercise.reading_text_source, exercise.reading_text_ocr_raw, exercise.reading_screenshot_asset_id, now()))
        ids = {}
        for sample in input_data.samples:
            sample_id = uid("sample")
            ids[sample.role] = sample_id
            db.execute("INSERT INTO response_samples (id,exercise_id,role,input_payload_json,created_at) VALUES (?,?,?,?,?)",
                       (sample_id, exercise_id, sample.role, "{}", now()))
            _write_view(db, sample_id, sample, 1)
        db.execute("INSERT INTO comparisons VALUES (?,?,?,?,?)",
                   (comparison_id, exercise_id, ids["user"], ids["benchmark"], now()))
    return get_comparison(path, comparison_id)


def update_sample(path, sample_id: str, expected_version: int, sample: SampleInput) -> dict | None:
    with connect(path) as db:
        row = db.execute("SELECT role,input_version FROM response_samples WHERE id=?", (sample_id,)).fetchone()
        if not row:
            return None
        if row["role"] != sample.role:
            raise ValueError("sample_role_cannot_change")
        if row["input_version"] != expected_version:
            raise ValueError("stale_sample_version")
        _assert_assets(db, sample)
        revision_id = _write_view(db, sample_id, sample, expected_version + 1)
    return {"id": sample_id, "version": expected_version + 1, "revision_id": revision_id, "sample": sample.model_dump(mode="json")}


def get_comparison(path, comparison_id: str) -> dict | None:
    with connect(path) as db:
        row = db.execute("SELECT c.*,e.question_type,e.title,e.source_note,e.source_question_id,e.reading_text_raw,e.reading_text_source,e.reading_text_ocr_raw,e.reading_screenshot_asset_id FROM comparisons c JOIN exercises e ON e.id=c.exercise_id WHERE c.id=?", (comparison_id,)).fetchone()
        if not row:
            return None
        samples = {}
        for role, sample_id in (("user", row["user_sample_id"]), ("benchmark", row["benchmark_sample_id"])):
            sample_row = db.execute("SELECT input_version,input_payload_json FROM response_samples WHERE id=?", (sample_id,)).fetchone()
            revision = db.execute("SELECT id FROM sample_revisions WHERE sample_id=? AND version=?", (sample_id, sample_row["input_version"])).fetchone()
            samples[role] = {"id": sample_id, "version": sample_row["input_version"], "revision_id": revision["id"],
                             "sample": json.loads(sample_row["input_payload_json"])}
        return {"id": comparison_id, "exercise_id": row["exercise_id"],
                "exercise": {k: row[k] for k in ("question_type", "title", "source_note", "source_question_id", "reading_text_raw", "reading_text_source", "reading_text_ocr_raw", "reading_screenshot_asset_id")},
                "created_at": row["created_at"], "samples": samples}


def list_history(path, limit: int = 50) -> list[dict]:
    with connect(path) as db:
        rows = db.execute("SELECT c.id,c.created_at,e.question_type,e.title FROM comparisons c JOIN exercises e ON e.id=c.exercise_id ORDER BY c.created_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]
