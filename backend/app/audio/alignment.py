"""Independent word alignment interface with conservative quality validation."""
import os
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from app.screenshots.mapper import normalize


class AlignmentProvider(Protocol):
    def align(self, wav_path: Path, tokens: list[dict], duration_s: float) -> dict: ...


class NoAlignment:
    def align(self, wav_path: Path, tokens: list[dict], duration_s: float) -> dict:
        return {"provider": "none", "status": "unavailable", "reason": "alignment_provider_disabled",
                "tokens": [{"index": token["index"], "start_s": None, "end_s": None, "quality": "unavailable"} for token in tokens]}


def tts_word_boundaries(tokens: list[dict], events: list[dict], duration_s: float) -> dict:
    """仅将生成服务返回的同形词事件映射到脚本；数字展开等差异不猜时间。"""
    words = [normalize(token["surface"]) for token in tokens]
    spoken = [normalize(event["text"]) for event in events]
    matched: dict[int, int] = {}
    for kind, left_start, left_end, right_start, right_end in SequenceMatcher(
            a=words, b=spoken, autojunk=False).get_opcodes():
        if kind == "equal":
            matched.update({index: right_start + index - left_start for index in range(left_start, left_end)})
    timed = []
    previous = 0.0
    for token in tokens:
        event = events[matched[token["index"]]] if token["index"] in matched else None
        valid = bool(event and 0 <= event["start_s"] < event["end_s"] <= duration_s + 0.1
                     and event["start_s"] >= previous - 0.03)
        timed.append({"index": token["index"], "start_s": round(event["start_s"], 3) if valid else None,
                      "end_s": round(event["end_s"], 3) if valid else None, "quality": "medium" if valid else "unreliable"})
        if valid:
            previous = event["end_s"]
    trusted = sum(item["quality"] == "medium" for item in timed)
    return {"provider": "edge-tts-word-boundary", "status": "complete" if trusted == len(tokens) else "partial",
            "reason": None if trusted == len(tokens) else "tts_word_boundary_mismatch",
            "trusted_count": trusted, "total_count": len(tokens), "tokens": timed,
            "limitations": ["词位置由合成服务提供，尚未通过独立语音识别核验。"]}


@lru_cache(maxsize=1)
def _model():
    import torch
    import whisperx

    torch.set_num_threads(min(4, os.cpu_count() or 1))
    return whisperx.load_align_model(language_code="en", device="cpu")


class WhisperXAlignment:
    def align(self, wav_path: Path, tokens: list[dict], duration_s: float) -> dict:
        import whisperx

        if not tokens:
            return {"provider": "whisperx-3.8.6", "status": "unavailable", "reason": "empty_transcript", "tokens": []}
        model, metadata = _model()
        audio = whisperx.load_audio(str(wav_path))
        transcript = " ".join(token["surface"] for token in tokens)
        result = whisperx.align([{"start": 0.0, "end": len(audio) / 16000, "text": transcript}], model, metadata, audio, "cpu", return_char_alignments=False)
        words = result.get("word_segments", [])
        if len(words) != len(tokens) or any(normalize(a["surface"]) != normalize(b.get("word", "")) for a, b in zip(tokens, words)):
            return {"provider": "whisperx-3.8.6", "status": "unavailable", "reason": "aligned_word_sequence_mismatch",
                    "tokens": NoAlignment().align(wav_path, tokens, duration_s)["tokens"]}
        timed = []
        previous_end = 0.0
        for token, word in zip(tokens, words):
            start, end, score = word.get("start"), word.get("end"), word.get("score", 0.0)
            valid = (start is not None and end is not None and 0 <= start < end <= duration_s + 0.1
                     and end - start <= 2.5 and start >= previous_end - 0.02)
            quality = "medium" if valid and score >= 0.5 else "unreliable"
            timed.append({"index": token["index"], "start_s": round(float(start), 3) if valid else None,
                          "end_s": round(float(end), 3) if valid else None, "quality": quality,
                          "alignment_score": round(float(score), 3)})
            if valid:
                previous_end = end
        trusted = sum(token["quality"] == "medium" for token in timed)
        return {"provider": "whisperx-3.8.6", "status": "complete" if trusted == len(timed) else "partial",
                "reason": None if trusted == len(timed) else "low_quality_word_timestamps",
                "trusted_count": trusted, "total_count": len(timed), "tokens": timed,
                "limitations": ["Alignment score is a model signal, not calibrated timestamp accuracy."]}


def create_alignment_provider(name: str, data_dir: Path | None = None) -> AlignmentProvider:
    if name == "whisperx":
        if data_dir is not None:
            # 容器可在镜像内预装模型；仅在未显式指定缓存时才回退到数据目录。
            os.environ.setdefault("NLTK_DATA", str(data_dir / "models/nltk"))
            os.environ.setdefault("TORCH_HOME", str(data_dir / "models/torch"))
            os.environ.setdefault("HF_HOME", str(data_dir / "models/hf"))
        return WhisperXAlignment()
    if name == "none":
        return NoAlignment()
    raise ValueError("unsupported_alignment_provider")
