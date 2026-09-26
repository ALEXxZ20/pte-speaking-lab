"""Cross-dimension rules only consume saved independent evidence."""
from uuid import uuid4

VERSION = "diagnosis-v1"


def _finding(kind: str, statement: str, recommendation: str, evidence_ids: list[str],
             confidence: str = "medium", severity: str = "medium", limitations: list[str] | None = None) -> dict:
    return {"id": f"finding_{uuid4().hex}", "kind": kind, "severity": severity,
            "confidence_level": confidence, "statement": statement,
            "recommendation": recommendation, "evidence_ids": evidence_ids,
            "limitations": limitations or [], "rule_version": VERSION}


def diagnose(user_pronunciation: dict, user_fluency: dict, comparison: dict,
             llm_provider=None, cross_window_ms: int = 750) -> dict:
    evidence = user_pronunciation["evidence"] + user_fluency["evidence"]
    known = {item["id"]: item for item in evidence}
    findings = []
    red = [item for item in user_pronunciation["evidence"] if item["kind"] == "xingji_word_color" and item["details"]["color"] == "red"]
    if red:
        provisional = any(item["details"].get("review_status") == "candidate" for item in red)
        findings.append(_finding("red_word_practice", f"截图识别出 {len(red)} 个红词候选，适合优先回听。" if provisional else f"猩际标出 {len(red)} 个已复核红词，适合优先回听。",
                                 "逐个回听红词所在短句，录制同一句两次，并观察下一次词色是否改善。",
                                 [item["id"] for item in red[:5]], severity="high", confidence="low" if provisional else "medium",
                                 limitations=["截图词色尚待人工复核。" if provisional else "颜色不能单独确定具体音素错误。"] ))
    pauses = [item for item in user_fluency["evidence"] if item["kind"] == "pause_candidate" and item["quality"] == "medium"
              and item["value"] >= 500]
    associations = []
    for word in red:
        if word.get("start_s") is None or word.get("end_s") is None:
            continue
        for pause in pauses:
            gap = max(pause["start_s"] - word["end_s"], word["start_s"] - pause["end_s"], 0)
            if gap * 1000 <= cross_window_ms:
                associations.append((word, pause))
                break
    if associations:
        ids = list(dict.fromkeys(id for word, pause in associations for id in (word["id"], pause["id"])))
        findings.append(_finding("pronunciation_associated_hesitation",
                                 "部分红词附近出现长停顿；两者可能相关。" if len(associations) == 1 else "多个红词附近出现长停顿，值得一起练习。",
                                 "回听这些位置，先单独练词，再把词放回原句连续表达。",
                                 ids, "low" if len(associations) == 1 else "medium",
                                 limitations=["时间接近不证明停顿由发音造成；也可能是句法或思考停顿。"] ))
    metrics = user_fluency["metrics"]
    long_pause = metrics.get("long_pause_count", {})
    if long_pause.get("value") and long_pause.get("quality") == "medium":
        ids = [item["id"] for item in user_fluency["evidence"] if item["kind"] == "pause_candidate" and item["value"] >= 500]
        if ids:
            findings.append(_finding("long_pause_practice", "回答中有可测量的长停顿。",
                                     "按意群练习连接前后短句，下次对比长停顿次数与位置。", ids[:5],
                                     limitations=["停顿可能是正常的语义分界。"] ))
    stability = metrics.get("rate_stability_cv", {})
    difference = comparison["fluency_metric_differences"].get("rate_stability_cv", {})
    if stability.get("quality") == "medium" and difference.get("delta_user_minus_benchmark") is not None and difference["delta_user_minus_benchmark"] > 0.15:
        ids = [item["id"] for item in user_fluency["evidence"] if item["kind"] == "metric_rate_stability_cv"]
        if ids:
            findings.append(_finding("rate_stability_practice", "这次回答的局部语速波动比 benchmark 更大。",
                                     "按意群重复录音，保持相近节奏；下次观察局部语速波动是否减小。", ids,
                                     limitations=["两侧表达内容不同；较稳不代表必须模仿对方语速。"] ))
    findings = findings[:3]
    llm_status = "disabled"
    if llm_provider and findings:
        try:
            proposed = llm_provider.explain(findings, [known[id] for finding in findings for id in finding["evidence_ids"]])
            by_id = {item["id"]: item for item in proposed}
            if set(by_id) != {item["id"] for item in findings}:
                raise ValueError("llm_finding_ids_mismatch")
            for finding in findings:
                candidate = by_id[finding["id"]]
                if candidate["evidence_ids"] != finding["evidence_ids"]:
                    raise ValueError("llm_evidence_ids_mismatch")
                finding["statement"] = candidate["statement"]
                finding["recommendation"] = candidate["recommendation"]
            llm_status = "used"
        except Exception:
            llm_status = "fallback_to_rules"
    assert all(id in known for finding in findings for id in finding["evidence_ids"])
    return {"rule_version": VERSION, "findings": findings, "llm_status": llm_status,
            "recommendations": [finding["recommendation"] for finding in findings]}
