"""Edge 在线朗读：保存成品音频和服务返回的词时间事件，不推测猩际评分。"""
import asyncio
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import re
import subprocess
import wave
from pathlib import Path

import numpy as np

from app.config import Settings
from app.persistence.database import connect
from app.persistence.samples import now, uid

VOICES = ("en-US-AriaNeural", "en-US-EmmaMultilingualNeural", "en-GB-RyanNeural")
try:
    EDGE_VERSION = version("edge-tts")
except PackageNotFoundError:
    EDGE_VERSION = None
VERSION = f"edge-tts-{EDGE_VERSION or 'unavailable'}-pcm-v2"
SAMPLE_RATE = 24000


def preview_segments(text: str, max_chars: int = 280) -> list[str]:
    """按原稿标点和段落断句；过长时才在逗号或词边界拆开。"""
    text = text.strip()
    if not text:
        return []
    sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
    segments: list[str] = []
    for sentence in sentences:
        sentence = " ".join(sentence.split())
        if not sentence:
            continue
        clauses = re.split(r"(?<=[,;:])\s+", sentence) if len(sentence) > max_chars else [sentence]
        for clause in clauses:
            words = clause.split()
            current = ""
            for word in words:
                if current and len(current) + len(word) + 1 > max_chars:
                    segments.append(current)
                    current = word
                else:
                    current = f"{current} {word}".strip()
            if current:
                segments.append(current)
    return segments


async def _request_segment(text: str, voice: str, rate: str, timeout_s: int) -> tuple[bytes, list[dict]]:
    """边接收音频边保留 WordBoundary；一次失败后有限重试。"""
    import edge_tts  # 延迟导入：TTS 依赖缺失不影响原有上传比较与报告。
    for attempt in range(2):
        audio = bytearray()
        boundaries = []
        try:
            async def collect():
                async for part in edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary").stream():
                    if part["type"] == "audio":
                        audio.extend(part["data"])
                    elif part["type"] == "WordBoundary":
                        boundaries.append({"text": part["text"], "start_s": part["offset"] / 10_000_000,
                                           "end_s": (part["offset"] + part["duration"]) / 10_000_000})
            await asyncio.wait_for(collect(), timeout_s)
            if not audio or not boundaries:
                raise RuntimeError("tts_empty_audio_or_boundaries")
            return bytes(audio), boundaries
        except Exception:
            if attempt:
                raise
            await asyncio.sleep(0.5)
    raise RuntimeError("tts_generation_failed")


def _decode_mp3(audio: bytes, settings: Settings) -> np.ndarray:
    """把在线返回的压缩音频统一转为 PCM，使段长和词时间共用采样基准。"""
    result = subprocess.run([settings.ffmpeg_bin, "-hide_banner", "-loglevel", "error", "-nostdin", "-i", "pipe:0",
                             "-f", "s16le", "-ac", "1", "-ar", str(SAMPLE_RATE), "pipe:1"],
                            input=audio, capture_output=True, timeout=30)
    if result.returncode or not result.stdout:
        raise RuntimeError("tts_audio_decode_failed")
    return np.frombuffer(result.stdout, dtype="<i2").copy()


def _quiet_edge_s(samples: np.ndarray, trailing: bool) -> float:
    """只测首尾安静区，用于补足断句间隔；从不裁掉发声音频。"""
    count = 0
    frame = 240  # 10 ms
    blocks = range(len(samples) - frame, -1, -frame) if trailing else range(0, len(samples) - frame, frame)
    for start in blocks:
        chunk = samples[start:start + frame].astype(np.float64)
        if np.sqrt(np.mean(chunk * chunk)) > 32768 * 0.01:
            break
        count += frame
    return count / SAMPLE_RATE


def _cache_key(segments: list[str], voice: str, rate: str, gap_ms: int) -> str:
    """把会影响合成结果的参数和 Provider 版本都纳入缓存键。"""
    payload = json.dumps([VERSION, segments, voice, rate, gap_ms], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def generate(segments: list[str], voice: str, rate: str, settings: Settings) -> dict:
    """分段生成并拼接成 WAV；所有词时间换算到成品文件的全局时间。"""
    if not settings.tts_enabled:
        raise ValueError("tts_disabled")
    if EDGE_VERSION is None:
        raise ValueError("tts_dependency_missing")
    segments = [" ".join(value.split()) for value in segments]
    if not segments or any(not item or len(item) > 350 for item in segments) or len(segments) > 50 or sum(map(len, segments)) > 6000:
        raise ValueError("tts_script_out_of_range")
    if voice not in VOICES or not re.fullmatch(r"[+-](?:[0-9]|[1-4][0-9]|50)%", rate):
        raise ValueError("tts_voice_or_rate_invalid")
    text = " ".join(segments)
    key = _cache_key(segments, voice, rate, settings.tts_gap_ms)
    with connect(settings.database_path) as db:
        cached = db.execute("SELECT * FROM tts_generations WHERE cache_key=?", (key,)).fetchone()
        if cached:
            audio = db.execute("SELECT relative_path FROM audio_assets WHERE id=?", (cached["audio_asset_id"],)).fetchone()
            if audio and (settings.data_dir / audio["relative_path"]).is_file():
                return _result(cached, cached=True)

    # 每一段独立请求，依据实测 PCM 长度累计偏移；补静音只发生在段与段之间。
    samples: list[np.ndarray] = []
    word_events: list[dict] = []
    seams: list[dict] = []
    offset_s = 0.0
    previous_pcm: np.ndarray | None = None
    for index, segment in enumerate(segments):
        encoded, local_events = asyncio.run(_request_segment(segment, voice, rate, settings.tts_timeout_s))
        pcm = _decode_mp3(encoded, settings)
        if previous_pcm is not None:
            natural_s = _quiet_edge_s(previous_pcm, True) + _quiet_edge_s(pcm, False)
            added_s = max(0, settings.tts_gap_ms / 1000 - natural_s)
            silence = np.zeros(round(added_s * SAMPLE_RATE), dtype="<i2")
            # 即使没有补零，独立合成的两段在接缝处也可能自带停顿。
            seams.append({"start_s": round(offset_s, 4), "end_s": round(offset_s + len(silence) / SAMPLE_RATE, 4),
                          "boundary_s": round(offset_s, 4), "kind": "tts_segment_boundary"})
            if len(silence):
                samples.append(silence)
                offset_s += len(silence) / SAMPLE_RATE
        for event in local_events:
            word_events.append({"text": event["text"], "start_s": round(offset_s + event["start_s"], 4),
                                "end_s": round(offset_s + event["end_s"], 4), "segment_index": index})
        samples.append(pcm)
        offset_s += len(pcm) / SAMPLE_RATE
        previous_pcm = pcm
    if offset_s > settings.max_audio_seconds:
        raise ValueError("tts_audio_too_long")
    asset_id = uid("audio")
    relative = f"audio/original/{asset_id}.wav"
    target = settings.data_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp.wav")
    try:
        with wave.open(str(temporary), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(SAMPLE_RATE)
            for part in samples:
                out.writeframes(part.tobytes())
        sha = hashlib.sha256(temporary.read_bytes()).hexdigest()
        temporary.replace(target)
        with connect(settings.database_path) as db:
            db.execute("INSERT INTO audio_assets VALUES (?,?,?,?,?,?,?,?)",
                       (asset_id, relative, sha, "Edge TTS 练习参考.wav", "audio/wav", offset_s, SAMPLE_RATE, now()))
            db.execute("INSERT INTO tts_generations VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                       (uid("tts"), key, asset_id, text, voice, rate, json.dumps(segments, ensure_ascii=False),
                        json.dumps(word_events, ensure_ascii=False), json.dumps(seams), VERSION, now()))
            row = db.execute("SELECT * FROM tts_generations WHERE audio_asset_id=?", (asset_id,)).fetchone()
        return _result(row, cached=False)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    finally:
        temporary.unlink(missing_ok=True)


def _result(row, cached: bool) -> dict:
    """将数据库 JSON 列还原为前端可审查的生成结果。"""
    return {"id": row["id"], "audio_asset_id": row["audio_asset_id"], "text": row["text"],
            "voice": row["voice"], "rate": row["rate"], "segments": json.loads(row["segments_json"]),
            "word_boundaries": json.loads(row["word_boundaries_json"]),
            "seam_intervals": json.loads(row["seam_intervals_json"]), "provider_version": row["provider_version"], "cached": cached}
