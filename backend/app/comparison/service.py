"""Compare independent results; benchmark is an observation, not a standard."""
from collections import defaultdict

VERSION = "comparison-v1"


def _quality(alignment: dict, index: int) -> bool:
    return any(token["index"] == index and token.get("quality") == "medium" for token in alignment.get("tokens", []))


def _color(token: dict) -> str:
    return token["color"] if token["color_review_status"] == "confirmed" else "unknown"


def shared_pairs(user: dict, benchmark: dict, user_alignment: dict, benchmark_alignment: dict,
                 user_pronunciation: dict, benchmark_pronunciation: dict) -> list[dict]:
    groups = defaultdict(lambda: {"user": [], "benchmark": []})
    for role, sample in (("user", user), ("benchmark", benchmark)):
        for token in sample["tokens"]:
            if token["normalized"]:
                groups[token["normalized"]][role].append(token)
    lookup = {}
    for role, result in (("user", user_pronunciation), ("benchmark", benchmark_pronunciation)):
        lookup[role] = {ev["token_index"]: ev["id"] for ev in result["evidence"] if ev["kind"] == "xingji_word_color"}
    pairs = []
    for word, sides in groups.items():
        candidates = []
        for left in sides["user"]:
            for right in sides["benchmark"]:
                left_color, right_color = _color(left), _color(right)
                score = (int(left_color != "unknown" and right_color != "unknown"),
                         int(left_color != right_color and "unknown" not in (left_color, right_color)),
                         int(_quality(user_alignment, left["index"])) + int(_quality(benchmark_alignment, right["index"])),
                         -abs(left["index"] - right["index"]))
                candidates.append((score, left, right))
        used_user, used_benchmark = set(), set()
        for _, left, right in sorted(candidates, key=lambda item: item[0], reverse=True):
            if left["index"] in used_user or right["index"] in used_benchmark:
                continue
            used_user.add(left["index"]); used_benchmark.add(right["index"])
            evidence_ids = [lookup[role].get(token["index"]) for role, token in (("user", left), ("benchmark", right))]
            pairs.append({"word": word, "user_index": left["index"], "benchmark_index": right["index"],
                          "user_color": _color(left), "benchmark_color": _color(right),
                          "user_timestamp_quality": "medium" if _quality(user_alignment, left["index"]) else "unavailable",
                          "benchmark_timestamp_quality": "medium" if _quality(benchmark_alignment, right["index"]) else "unavailable",
                          "evidence_ids": [id for id in evidence_ids if id],
                          "limitation": "Same word form in different sentences; duration alone does not establish pronunciation quality."})
    return sorted(pairs, key=lambda pair: pair["user_index"])


def compare(user_sample: dict, benchmark_sample: dict, user_alignment: dict, benchmark_alignment: dict,
            user_pronunciation: dict, benchmark_pronunciation: dict, user_fluency: dict, benchmark_fluency: dict) -> dict:
    pairs = shared_pairs(user_sample, benchmark_sample, user_alignment, benchmark_alignment,
                         user_pronunciation, benchmark_pronunciation)
    distributions = {}
    for role, result in (("user", user_pronunciation), ("benchmark", benchmark_pronunciation)):
        distributions[role] = result["summary"]
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
            "shared_word_pairs": pairs, "fluency_metric_differences": metric_differences,
            "limitations": ["Benchmark text and difficulty may differ; these are observed differences, not target thresholds."]}
