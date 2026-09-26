"""Position-aware comparison of observed transcripts and independent measurements."""
from app.screenshots.mapper import tokenize

VERSION = "comparison-v2"


def _quality(alignment: dict, index: int) -> bool:
    return any(token["index"] == index and token.get("quality") == "medium" for token in alignment.get("tokens", []))


def _color(token: dict) -> str:
    return token["color"] if token["color_review_status"] in {"confirmed", "candidate"} else "unknown"


def _ordered_matches(left: list[str], right: list[str]) -> list[tuple[int, int]]:
    """LCS pairs occurrences in reading order; repeated words are never paired by color."""
    n, m = len(left), len(right)
    lengths = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            lengths[i][j] = 1 + lengths[i + 1][j + 1] if left[i] == right[j] else max(lengths[i + 1][j], lengths[i][j + 1])
    result = []
    i = j = 0
    while i < n and j < m:
        if left[i] == right[j]:
            result.append((i, j))
            i += 1
            j += 1
        elif lengths[i + 1][j] >= lengths[i][j + 1]:
            i += 1
        else:
            j += 1
    return result


def _pair_indices(user: dict, benchmark: dict, reading_text_raw: str | None) -> tuple[list[tuple[int, int]], dict]:
    user_words = [item["normalized"] for item in user["tokens"]]
    benchmark_words = [item["normalized"] for item in benchmark["tokens"]]
    script_words = [item["normalized"] for item in tokenize(reading_text_raw or "")]
    if script_words:
        user_map = {script_index: sample_index for script_index, sample_index in _ordered_matches(script_words, user_words)}
        benchmark_map = {script_index: sample_index for script_index, sample_index in _ordered_matches(script_words, benchmark_words)}
        pairs = [(user_map[index], benchmark_map[index]) for index in sorted(user_map.keys() & benchmark_map.keys())]
        last_user = max(user_map, default=-1)
        last_benchmark = max(benchmark_map, default=-1)
        return pairs, {"basis": "shared_reading_text", "script_word_count": len(script_words),
                       "user_matched_script_words": len(user_map), "benchmark_matched_script_words": len(benchmark_map),
                       "shared_script_words": len(pairs),
                       "user_unmatched_transcript_words": len(user_words) - len(user_map),
                       "benchmark_unmatched_transcript_words": len(benchmark_words) - len(benchmark_map),
                       "user_script_tail_unobserved": max(0, len(script_words) - last_user - 1),
                       "benchmark_script_tail_unobserved": max(0, len(script_words) - last_benchmark - 1),
                       "limitation": "Transcript/script mismatch can result from delivery, recognition, or truncation; it is not proof of pronunciation error."}
    pairs = _ordered_matches(user_words, benchmark_words)
    return pairs, {"basis": "observed_transcripts_only", "script_word_count": None,
                   "user_matched_script_words": None, "benchmark_matched_script_words": None,
                   "shared_script_words": len(pairs),
                   "user_unmatched_transcript_words": len(user_words) - len(pairs),
                   "benchmark_unmatched_transcript_words": len(benchmark_words) - len(pairs),
                   "user_script_tail_unobserved": None, "benchmark_script_tail_unobserved": None,
                   "limitation": "No shared reading text was supplied; identical observed words are paired in order only."}


def shared_pairs(user: dict, benchmark: dict, user_alignment: dict, benchmark_alignment: dict,
                 user_pronunciation: dict, benchmark_pronunciation: dict,
                 reading_text_raw: str | None = None) -> list[dict]:
    indices, _ = _pair_indices(user, benchmark, reading_text_raw)
    lookup = {role: {ev["token_index"]: ev["id"] for ev in result["evidence"] if ev["kind"] == "xingji_word_color"}
              for role, result in (("user", user_pronunciation), ("benchmark", benchmark_pronunciation))}
    pairs = []
    for user_index, benchmark_index in indices:
        left, right = user["tokens"][user_index], benchmark["tokens"][benchmark_index]
        evidence_ids = [lookup[role].get(index) for role, index in (("user", user_index), ("benchmark", benchmark_index))]
        pairs.append({"word": left["normalized"], "user_index": user_index, "benchmark_index": benchmark_index,
                      "user_color": _color(left), "benchmark_color": _color(right),
                      "user_timestamp_quality": "medium" if _quality(user_alignment, user_index) else "unavailable",
                      "benchmark_timestamp_quality": "medium" if _quality(benchmark_alignment, benchmark_index) else "unavailable",
                      "evidence_ids": [item for item in evidence_ids if item],
                      "limitation": "Same intended word; color and timing differences do not by themselves establish a phoneme error."})
    return pairs


def compare(user_sample: dict, benchmark_sample: dict, user_alignment: dict, benchmark_alignment: dict,
            user_pronunciation: dict, benchmark_pronunciation: dict, user_fluency: dict, benchmark_fluency: dict,
            reading_text_raw: str | None = None) -> dict:
    pairs = shared_pairs(user_sample, benchmark_sample, user_alignment, benchmark_alignment,
                         user_pronunciation, benchmark_pronunciation, reading_text_raw)
    _, transcript_comparison = _pair_indices(user_sample, benchmark_sample, reading_text_raw)
    distributions = {role: result["summary"] for role, result in (("user", user_pronunciation), ("benchmark", benchmark_pronunciation))}
    metric_differences = {}
    for key, left in user_fluency["metrics"].items():
        right = benchmark_fluency["metrics"].get(key)
        if right is None:
            continue
        valid = left["value"] is not None and right["value"] is not None and left["unit"] == right["unit"]
        metric_differences[key] = {"user": left, "benchmark": right,
                                   "delta_user_minus_benchmark": round(left["value"] - right["value"], 3) if valid else None,
                                   "quality": "low" if "low" in (left["quality"], right["quality"]) else "medium" if valid else "unavailable",
                                   "reason": None if valid else "metric_missing_or_unit_mismatch"}
    return {"algorithm_version": VERSION, "pronunciation_distribution_comparison": distributions,
            "shared_word_pairs": pairs, "transcript_comparison": transcript_comparison,
            "fluency_metric_differences": metric_differences,
            "limitations": ["AI-generated benchmark is an observed reference, not a pronunciation standard.",
                            "Transcript omissions or changed words are not automatically pronunciation errors."]}
