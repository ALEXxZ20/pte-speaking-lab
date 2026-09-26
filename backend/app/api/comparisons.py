import json

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.domain.schemas import ComparisonInput, SampleUpdate
from app.persistence.database import connect
from app.persistence.deletion import delete_comparison, preview_deletion
from app.persistence.samples import create_comparison, get_comparison, list_history, now, uid, update_sample
from app.screenshots.mapper import map_screenshot, preview_screenshot

router = APIRouter(prefix="/api/v1", tags=["comparisons"])


def problem(code: str, status: int = 422):
    raise HTTPException(status_code=status, detail={"code": code, "message": code.replace("_", " ")})


@router.post("/comparisons")
def create(body: ComparisonInput, request: Request) -> dict:
    try:
        return create_comparison(request.app.state.settings.database_path, body)
    except ValueError as exc:
        problem(str(exc))


@router.get("/comparisons/{comparison_id}")
def read(comparison_id: str, request: Request) -> dict:
    result = get_comparison(request.app.state.settings.database_path, comparison_id)
    if result is None:
        problem("comparison_not_found", 404)
    return result


@router.get("/history")
def history(request: Request, limit: int = 50) -> list[dict]:
    return list_history(request.app.state.settings.database_path, max(1, min(limit, 100)))


@router.get("/comparisons/{comparison_id}/deletion-preview")
def deletion_preview(comparison_id: str, request: Request) -> dict:
    result = preview_deletion(request.app.state.settings.database_path, comparison_id)
    if result is None:
        problem("comparison_not_found", 404)
    return result


@router.delete("/comparisons/{comparison_id}")
def delete(comparison_id: str, request: Request) -> dict:
    settings = request.app.state.settings
    result = delete_comparison(settings.database_path, settings.data_dir, comparison_id)
    if result is None:
        problem("comparison_not_found", 404)
    return result


@router.patch("/samples/{sample_id}")
def patch_sample(sample_id: str, body: SampleUpdate, request: Request) -> dict:
    try:
        result = update_sample(request.app.state.settings.database_path, sample_id, body.expected_version, body.sample)
    except ValueError as exc:
        problem(str(exc), 409 if str(exc) == "stale_sample_version" else 422)
    if result is None:
        problem("sample_not_found", 404)
    return result


class ImportRequest(BaseModel):
    screenshot_id: str


class PreviewRequest(BaseModel):
    kind: str = "xingji"
    transcript_override: str | None = None


@router.post("/screenshots/{screenshot_id}/preview")
def preview(screenshot_id: str, body: PreviewRequest, request: Request) -> dict:
    settings = request.app.state.settings
    with connect(settings.database_path) as db:
        row = db.execute("SELECT relative_path FROM screenshot_assets WHERE id=?", (screenshot_id,)).fetchone()
    if not row:
        problem("screenshot_not_found", 404)
    path = settings.data_dir / row["relative_path"]
    try:
        result = preview_screenshot(path, screenshot_id, body.kind, transcript_override=body.transcript_override)
        return result
    except RuntimeError as exc:
        if str(exc) == "screenshot_ocr_unavailable":
            problem("screenshot_ocr_unavailable", 503)
        raise
    except ValueError as exc:
        problem(str(exc))


@router.post("/samples/{sample_id}/screenshot-imports")
def import_screenshot(sample_id: str, body: ImportRequest, request: Request) -> dict:
    settings = request.app.state.settings
    with connect(settings.database_path) as db:
        sample = db.execute("SELECT transcript_raw,input_payload_json FROM response_samples WHERE id=?", (sample_id,)).fetchone()
        screenshot = db.execute("SELECT relative_path FROM screenshot_assets WHERE id=?", (body.screenshot_id,)).fetchone()
        if not sample or not screenshot:
            problem("sample_or_screenshot_not_found", 404)
        if not sample["transcript_raw"]:
            problem("transcript_required")
        payload = json.loads(sample["input_payload_json"])
        if body.screenshot_id not in payload["color_screenshot_asset_ids"]:
            problem("screenshot_not_attached_to_sample")
    try:
        draft = map_screenshot(sample["transcript_raw"], settings.data_dir / screenshot["relative_path"], body.screenshot_id)
    except RuntimeError as exc:
        if str(exc) == "screenshot_ocr_unavailable":
            problem("screenshot_ocr_unavailable", 503)
        raise
    except ValueError as exc:
        problem(str(exc))
    import_id = uid("import")
    with connect(settings.database_path) as db:
        db.execute("INSERT INTO screenshot_imports VALUES (?,?,?,?,?)", (import_id, sample_id, draft["parser_version"], json.dumps(draft), now()))
    return {"id": import_id, "draft": draft}


@router.get("/samples/{sample_id}/screenshot-imports")
def list_screenshot_imports(sample_id: str, request: Request) -> list[dict]:
    with connect(request.app.state.settings.database_path) as db:
        if not db.execute("SELECT 1 FROM response_samples WHERE id=?", (sample_id,)).fetchone():
            problem("sample_not_found", 404)
        rows = db.execute("SELECT id,draft_json,created_at FROM screenshot_imports WHERE sample_id=? ORDER BY created_at", (sample_id,)).fetchall()
        return [{"id": row["id"], "draft": json.loads(row["draft_json"]), "created_at": row["created_at"]} for row in rows]
