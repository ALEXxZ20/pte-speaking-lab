"""Pronunciation evidence runs without any fluency result."""
from pathlib import Path
from typing import Protocol

from app.engines.common import evidence

VERSION = "pronunciation-v1"


class PronunciationProvider(Protocol):
    name: str
    def assess(self, wav_path: Path, tokens: list[dict], timed_tokens: list[dict], target_index: int) -> dict: ...


def analyze_pronunciation(sample_id: str, sample: dict, alignment: dict, wav_path: Path | None = None,
                          provider: PronunciationProvider | None = None, target_limit: int = 12) -> dict:
    tokens = sample["tokens"]
    confirmed = [token for token in tokens if token["color_review_status"] == "confirmed" and token["color"] != "unknown"]
    counts = {color: sum(token["color"] == color for token in confirmed) for color in ("red", "yellow", "green")}
    timed = {token["index"]: token for token in alignment.get("tokens", [])}
    targets = sorted((token for token in confirmed if token["color"] in {"red", "yellow"}),
                     key=lambda token: (0 if token["color"] == "red" else 1, token["index"]))[:target_limit]
    items = []
    color_evidence = {}
    for token in confirmed:
        time = timed.get(token["index"], {})
        valid_time = time.get("quality") == "medium"
        start = time.get("start_s") if valid_time else None
        end = time.get("end_s") if valid_time else None
        color_ev = evidence(sample_id, "pronunciation", "xingji_word_color", "external",
                            token.get("color_source_screenshot_id") or "xingji:manual", "high", VERSION,
                            token_index=token["index"], start_s=start, end_s=end, value=None, unit=None,
                            details={"surface": token["surface"], "color": token["color"], "timestamp_quality": time.get("quality", "unavailable")})
        items.append(color_ev)
        color_evidence[token["index"]] = color_ev["id"]
    output_targets = []
    for token in targets:
        time = timed.get(token["index"], {})
        valid_time = time.get("quality") == "medium"
        start = time.get("start_s") if valid_time else None
        end = time.get("end_s") if valid_time else None
        target = {"index": token["index"], "surface": token["surface"], "color": token["color"],
                  "start_s": start, "end_s": end, "timestamp_quality": time.get("quality", "unavailable"),
                  "evidence_ids": [color_evidence[token["index"]]]}
        if provider and wav_path and valid_time:
            try:
                signal = provider.assess(wav_path, tokens, alignment["tokens"], token["index"])
                model_ev = evidence(sample_id, "pronunciation", "phoneme_model_candidate", "model_signal", provider.name,
                                    "low", VERSION, token_index=token["index"], start_s=start, end_s=end,
                                    value=None, unit=None, details=signal)
                items.append(model_ev)
                target["evidence_ids"].append(model_ev["id"])
            except Exception as exc:
                target["provider_error"] = type(exc).__name__
        output_targets.append(target)
    total = len(confirmed)
    return {"dimension": "pronunciation", "algorithm_version": VERSION,
            "status": "complete" if total else "partial",
            "summary": {"counts": counts, "known_count": total, "unknown_count": len(tokens) - total,
                        "ratios": {color: round(counts[color] / total, 4) if total else None for color in counts},
                        "xingji_score": sample.get("pronunciation_score"),
                        "limitation": "Only confirmed Xingji colors are counted; word colors do not identify a phoneme error."},
            "targets": output_targets, "evidence": items,
            "provider": provider.name if provider else "none"}
