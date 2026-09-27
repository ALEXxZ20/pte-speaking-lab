"""TTS 预览与生成接口；生成音频始终明确标记为练习参考。"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.providers.edge_tts import EDGE_VERSION, VOICES, generate, preview_segments

router = APIRouter(prefix="/api/v1/tts", tags=["tts"])


class PreviewRequest(BaseModel):
    text: str = Field(min_length=1, max_length=6000)


class GenerateRequest(BaseModel):
    segments: list[str] = Field(min_length=1, max_length=50)
    voice: str = "en-US-AriaNeural"
    rate: str = "+0%"


@router.get("/settings")
def settings(request: Request) -> dict:
    """只公开 TTS 可用状态与非敏感选项；不泄露后端密钥。"""
    current = request.app.state.settings
    return {"enabled": current.tts_enabled and EDGE_VERSION is not None, "voices": VOICES, "default_voice": current.tts_voice,
            "default_rate": current.tts_rate, "gap_ms": current.tts_gap_ms,
            "notice": "朗读稿会发送到 Microsoft Edge 在线语音服务；合成音未经过猩际评分。"}


@router.post("/segments")
def segments(body: PreviewRequest) -> dict:
    """预览建议分段，最终分段仍由用户核对后提交。"""
    return {"segments": preview_segments(body.text)}


@router.post("/generations")
def create_generation(body: GenerateRequest, request: Request) -> dict:
    """在线生成失败时给出可重试错误，不影响原有上传比较。"""
    try:
        return generate(body.segments, body.voice, body.rate, request.app.state.settings)
    except ValueError as exc:
        raise HTTPException(422, detail={"code": str(exc), "message": str(exc).replace("_", " ")}) from exc
    except Exception as exc:
        raise HTTPException(503, detail={"code": "tts_generation_failed", "message": "在线朗读暂不可用，请稍后重试"}) from exc
