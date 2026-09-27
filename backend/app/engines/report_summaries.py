"""把本次报告的实测证据整理成可追溯的中文总结；AI 只负责可选改写。"""
import re

VERSION = "report-summaries-v2"


def _local_fluency(comparison: dict) -> tuple[str, list[str]]:
    """按可信度选取本次双边指标；低质量候选必须连同限制一起呈现。"""
    metrics = comparison["fluency_metric_differences"]
    used: list[str] = []
    sentences: list[str] = []
    wpm = metrics.get("wpm")
    if wpm and wpm["delta_user_minus_benchmark"] is not None:
        used.append("wpm")
        left, right = wpm["user"]["value"], wpm["benchmark"]["value"]
        direction = "较快" if left > right else "较慢" if left < right else "相同"
        sentences.append(f"本次整体词速为我的 {left:g}、参考 {right:g} WPM；我的回答{direction}。不要仅凭速度差决定是否加快朗读。")
    pauses = metrics.get("long_pause_count")
    if pauses and pauses["delta_user_minus_benchmark"] is not None:
        used.append("long_pause_count")
        left, right = pauses["user"]["value"], pauses["benchmark"]["value"]
        qualifier = "词间隔推算，质量低；先回听具体位置，不把次数当成已确认的静音。" if pauses["quality"] == "low" else "请结合句意判断这些位置是否需要停顿。"
        sentences.append(f"长停顿候选为我的 {left:g} 次、参考 {right:g} 次；{qualifier}")
    stability = metrics.get("rate_stability_cv")
    if stability and stability["delta_user_minus_benchmark"] is not None and stability["quality"] in {"high", "medium"}:
        used.append("rate_stability_cv")
        left, right = stability["user"]["value"], stability["benchmark"]["value"]
        if abs(left - right) < 0.05:
            sentences.append(f"局部语速波动系数为 {left:g} 与 {right:g}，差距较小；本次没有依据要求刻意模仿参考语速。")
        else:
            sentences.append(f"局部语速波动系数为我的 {left:g}、参考 {right:g}；可回听语速明显变化的句段。")
    if not sentences:
        sentences.append("本次缺少足够可靠的双边时间数据；先核查转写是否完整、词级对齐是否可用。")
    if any(item["user"].get("reason") == "vad_regions_unreliable" for item in metrics.values()):
        sentences.append("我的录音语音活动检测未能可靠分开语音与静音，所以本次不比较发声占比和语音/静音比。")
    return " ".join(sentences), used


def _local_practice(diagnosis: dict, pronunciation: dict, fluency: dict) -> tuple[str, list[str], list[dict]]:
    """只从这次的红黄词和可定位停顿取例子，不猜元音、辅音或停顿原因。"""
    findings = diagnosis["findings"][:3]
    colors = [item for item in pronunciation["evidence"] if item["kind"] == "xingji_word_color"
              and item["details"].get("color") in {"red", "yellow"}]
    red = [item for item in colors if item["details"]["color"] == "red"]
    # 优先选能可靠回听的词，再按录音时间选最早几个；没有时间的位置仍可列词但不伪造秒数。
    selected = sorted(red or colors, key=lambda item: (item.get("start_s") is None, item.get("start_s") or 0))[:3]
    facts = [{"id": item["id"], "word": item["details"]["surface"],
              "color": item["details"]["color"], "time_s": item.get("start_s"),
              "quality": item["quality"]} for item in selected]
    sentences = []
    if selected:
        count = len(red or colors)
        kind = "红词" if red else "黄词"
        source = "截图候选" if any(item["details"].get("review_status") == "candidate" for item in selected) else "已复核"
        examples = "、".join(f"{item['word']}（{item['time_s']:.2f} 秒）" if item["time_s"] is not None else item["word"] for item in facts)
        sentences.append(f"这次有 {count} 个{source}{kind}，先回听 {examples} 所在的完整短句；有可靠双边同词时再听参考。各重录同一句两次，检查词色及整句是否更容易听清。")
    pauses = [item for item in fluency["evidence"] if item["kind"] == "pause_candidate" and item["value"] is not None and item["value"] >= 500]
    if pauses:
        # 只选最值得核查的一处最长候选，避免把低质量的全部词间隙当成教学结论。
        first = max(pauses, key=lambda item: item["value"])
        if first["quality"] == "low":
            sentences.append(f"在 {first['start_s']:.2f} 秒附近还有词间长停顿候选，但定位质量低；先回听是否真的静音，再决定是否练意群连接。")
        else:
            sentences.append(f"在 {first['start_s']:.2f} 秒附近有长停顿，回听它是否处于自然的意思分界。")
        facts.append({"id": first["id"], "kind": "pause_candidate", "time_s": first["start_s"], "quality": first["quality"]})
    if not sentences:
        sentences.append("本次没有足够的可定位红黄词或停顿证据，不能给出具体发音错误判断；先检查截图词色和词级时间。")
    return " ".join(sentences), [finding["id"] for finding in findings], facts


def build_summaries(comparison: dict, diagnosis: dict, pronunciation: dict, fluency: dict, llm_provider=None) -> dict:
    """先保存本机总结，再尝试 AI；模型失败或引用越界时完整回退。"""
    fluency_text, metric_keys = _local_fluency(comparison)
    practice_text, finding_ids, facts = _local_practice(diagnosis, pronunciation, fluency)
    result = {"version": VERSION,
              "fluency": {"text": fluency_text, "source": "local_rules", "metric_keys": metric_keys},
              "practice": {"text": practice_text, "source": "local_rules", "finding_ids": finding_ids,
                           "evidence_ids": [fact["id"] for fact in facts]}}
    if llm_provider is None:
        return result
    try:
        proposal = llm_provider.summarize_report(
            {key: comparison["fluency_metric_differences"][key] for key in metric_keys},
            diagnosis["findings"], facts, fluency_text, practice_text)
        left, right = proposal["fluency"], proposal["practice"]
        # 模型只可引用已送出的指标和结论；禁止新增数字及具体音素诊断。
        if (set(left["metric_keys"]) - set(metric_keys) or
                set(right["finding_ids"]) - set(finding_ids) or
                (metric_keys and not left["metric_keys"]) or
                (finding_ids and not right["finding_ids"]) or
                not left["text"].strip() or not right["text"].strip() or
                len(left["text"]) > 500 or len(right["text"]) > 500 or
                re.search(r"\d|音素错误|元音错误|辅音错误|吞音|读错", left["text"] + right["text"]) or
                (metric_keys and not re.search(r"词速|停顿|语速|节奏", left["text"])) or
                (any(fact.get("word") for fact in facts) and
                 not any(fact.get("word") in right["text"] for fact in facts if fact.get("word")))):
            raise ValueError("summary_reference_validation_failed")
        result["fluency"] = {"text": left["text"], "source": "ai", "metric_keys": left["metric_keys"]}
        result["practice"] = {"text": right["text"], "source": "ai", "finding_ids": right["finding_ids"],
                              "evidence_ids": [fact["id"] for fact in facts]}
    except Exception:
        result["fallback_reason"] = "ai_unavailable_or_invalid"
    return result
