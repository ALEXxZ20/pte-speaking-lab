import json
import importlib.util

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.analysis.runner import run_comparison
from app.persistence.database import connect

router = APIRouter(prefix="/api/v1", tags=["analysis"])


class RunRequest(BaseModel):
    allow_cloud: bool = False
    use_openpronounce: bool = False


@router.post("/comparisons/{comparison_id}/runs")
def start_run(comparison_id: str, body: RunRequest, request: Request) -> dict:
    try:
        return run_comparison(comparison_id, request.app.state.settings, body.allow_cloud, body.use_openpronounce)
    except ValueError as exc:
        code = str(exc)
        status = 404 if code == "comparison_not_found" else 409 if code == "analysis_already_running" else 422
        raise HTTPException(status_code=status, detail={"code": code, "message": code.replace("_", " ")}) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail={"code": "local_dependency_missing", "message": "缺少本地音频工具或模型"}) from exc


@router.get("/runs/{run_id}")
def get_run(run_id: str, request: Request) -> dict:
    with connect(request.app.state.settings.database_path) as db:
        row = db.execute("SELECT id,comparison_id,status,pipeline_version,error_json,started_at,finished_at FROM analysis_runs WHERE id=?", (run_id,)).fetchone()
    if not row:
        raise HTTPException(404, detail={"code": "run_not_found", "message": "分析不存在"})
    return {**dict(row), "error": json.loads(row["error_json"]) if row["error_json"] else None}


@router.get("/runs/{run_id}/report")
def get_report(run_id: str, request: Request) -> dict:
    with connect(request.app.state.settings.database_path) as db:
        row = db.execute("SELECT result_json FROM comparisons_result WHERE run_id=?", (run_id,)).fetchone()
    if not row:
        raise HTTPException(404, detail={"code": "report_not_found", "message": "报告尚未生成"})
    return json.loads(row["result_json"])


@router.get("/runs/{run_id}/audio/{role}")
def play_prepared(run_id: str, role: str, request: Request):
    if role not in {"user", "benchmark"}:
        raise HTTPException(404, detail={"code": "role_not_found"})
    report = get_report(run_id, request)
    relative = report["samples"][role]["audio"]["wav_path"]
    path = (request.app.state.settings.data_dir / relative).resolve()
    if not path.is_relative_to(request.app.state.settings.data_dir / "audio/derived"):
        raise HTTPException(500, detail={"code": "invalid_audio_path"})
    return FileResponse(path, media_type="audio/wav")


@router.get("/comparisons/{comparison_id}/runs")
def list_runs(comparison_id: str, request: Request) -> list[dict]:
    with connect(request.app.state.settings.database_path) as db:
        rows = db.execute("SELECT id,status,started_at,finished_at FROM analysis_runs WHERE comparison_id=? ORDER BY started_at DESC", (comparison_id,)).fetchall()
    return [dict(row) for row in rows]


@router.get("/settings/providers")
def provider_settings(request: Request) -> dict:
    settings = request.app.state.settings
    return {"alignment": settings.alignment_provider,
            "pronunciation": settings.pronunciation_provider,
            "llm": settings.llm_provider,
            "openai_model": settings.openai_analysis_model or None,
            "openai_key_configured": bool(settings.openai_api_key.get_secret_value().strip()),
            "llm_base_url_configured": bool(settings.openai_base_url.strip()) if settings.llm_provider == "openai_compatible" else True,
            "openpronounce_available": importlib.util.find_spec("openpronounce") is not None,
            "cloud_requires_explicit_run_choice": True}
