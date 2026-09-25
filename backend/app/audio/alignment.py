"""Independent word alignment interface with conservative quality validation."""
import os
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
            os.environ.setdefault("NLTK_DATA", str(data_dir / "models/nltk"))
            os.environ.setdefault("TORCH_HOME", str(data_dir / "models/torch"))
            os.environ.setdefault("HF_HOME", str(data_dir / "models/hf"))
        return WhisperXAlignment()
    if name == "none":
        return NoAlignment()
    raise ValueError("unsupported_alignment_provider")
