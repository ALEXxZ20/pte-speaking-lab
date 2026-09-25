import sqlite3
import subprocess
from typing import Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from app.config import Settings
from app.persistence.database import connect

router = APIRouter(prefix="/api/v1", tags=["system"])


class Check(BaseModel):
    status: Literal["ok", "missing", "error", "disabled", "not_implemented"]
    detail: str


class ProviderCheck(BaseModel):
    name: str
    status: Literal["disabled", "available", "configured", "not_implemented"]
    configured: bool
    connectivity: Literal["not_tested"] = "not_tested"


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    api: Check
    database: Check
    ffmpeg: Check
    ffprobe: Check
    providers: dict[str, ProviderCheck]


def check_binary(binary: str) -> Check:
    try:
        result = subprocess.run([binary, "-version"], capture_output=True, timeout=3, check=False)
        if result.returncode == 0:
            return Check(status="ok", detail="可运行")
        return Check(status="error", detail="版本检查失败")
    except FileNotFoundError:
        return Check(status="missing", detail="未安装或路径不可用")
    except (OSError, subprocess.TimeoutExpired):
        return Check(status="error", detail="无法运行或检查超时")


def provider_checks(settings: Settings) -> dict[str, ProviderCheck]:
    result = {}
    for kind, name in {
        "llm": settings.llm_provider,
        "alignment": settings.alignment_provider,
        "pronunciation": settings.pronunciation_provider,
        "asr": settings.asr_provider,
    }.items():
        disabled = name == "none"
        configured = bool(
            kind == "llm" and name == "openai"
            and settings.openai_api_key.get_secret_value().strip()
            and settings.openai_analysis_model.strip()
        )
        supported = ((kind == "llm" and name == "openai") or
                     (kind == "alignment" and name == "whisperx") or
                     (kind == "pronunciation" and name == "openpronounce"))
        result[kind] = ProviderCheck(
            name=name if name in {"none", "openai", "whisperx", "openpronounce"} else "unsupported",
            status="disabled" if disabled else "configured" if configured else "available" if supported else "not_implemented",
            configured=configured,
        )
    return result


@router.get("/health")
def health(request: Request, response: Response) -> Health:
    settings = request.app.state.settings
    try:
        with connect(settings.database_path) as connection:
            connection.execute("SELECT value FROM app_metadata WHERE key='schema_scope'").fetchone()
            foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
            if foreign_keys != 1:
                raise sqlite3.DatabaseError("Foreign keys disabled")
        database = Check(status="ok", detail="数据库可读，外键约束已启用")
    except (OSError, sqlite3.Error):
        database = Check(status="error", detail="数据库不可用")
        response.status_code = 503
    ffmpeg, ffprobe = check_binary(settings.ffmpeg_bin), check_binary(settings.ffprobe_bin)
    return Health(
        status="ok" if all(check.status == "ok" for check in [database, ffmpeg, ffprobe]) else "degraded",
        api=Check(status="ok", detail="本机 API 可用"), database=database,
        ffmpeg=ffmpeg, ffprobe=ffprobe, providers=provider_checks(settings),
    )
