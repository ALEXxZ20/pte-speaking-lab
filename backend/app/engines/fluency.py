"""Fluency measurements run without any pronunciation result."""
from statistics import mean, pstdev

from app.engines.common import evidence, metric

VERSION = "fluency-v2"


def analyze_fluency(sample_id: str, sample: dict, audio: dict, alignment: dict,
                    pause_min_ms: int = 250, long_pause_ms: int = 500, very_long_pause_ms: int = 1000) -> dict:
    tokens = sample["tokens"]
    timed = {token["index"]: token for token in alignment.get("tokens", []) if token.get("quality") == "medium"}
    ordered = [timed[i] for i in range(len(tokens)) if i in timed]
    output = {}
    items = []
    regions = audio["speech_regions"]
    usable_vad = regions["quality"] == "medium" and len(regions["regions"]) >= 2
    trusted_window = len(ordered) >= 2 and 0 in timed and len(tokens) - 1 in timed
    if trusted_window:
        first, last = timed[0]["start_s"], timed[len(tokens) - 1]["end_s"]
        window = last - first
        output["wpm"] = metric(round(len(tokens) * 60 / window, 2), "words/min", "medium", duration_s=round(window, 3), word_count=len(tokens)) if window > 0 else metric(None, "words/min", "unavailable", "zero_speech_window")
        items.append(evidence(sample_id, "fluency", "speech_window", "measured", alignment["provider"], "medium", VERSION,
                              start_s=first, end_s=last, value=window, unit="s", details={"word_count": len(tokens)}))
    elif usable_vad:
        first, last = regions["regions"][0]["start_s"], regions["regions"][-1]["end_s"]
        window = last - first
        output["wpm"] = metric(round(len(tokens) * 60 / window, 2), "words/min", "medium", duration_s=round(window, 3), word_count=len(tokens), basis="vad_speech_span")
        items.append(evidence(sample_id, "fluency", "speech_window", "measured", "webrtcvad", "medium", VERSION,
                              start_s=first, end_s=last, value=window, unit="s", details={"word_count": len(tokens)}))
    else:
        output["wpm"] = metric(None, "words/min", "unavailable", "no_reliable_speech_window")
    gap_source = "webrtcvad" if usable_vad else "alignment_word_gaps"
    if usable_vad:
        pairs = [(regions["regions"][i - 1]["end_s"], regions["regions"][i]["start_s"])
                 for i in range(1, len(regions["regions"]))]
        gap_quality = "medium"
    else:
        pairs = [(timed[i - 1]["end_s"], timed[i]["start_s"])
                 for i in range(1, len(tokens)) if i - 1 in timed and i in timed]
        gap_quality = "low" if pairs else "unavailable"
    seams = audio.get("tts", {}).get("seam_intervals", [])
    # 合成时补入的静音是制作痕迹，不能写成说话者自然停顿。
    if seams:
        pairs = [(start, end) for start, end in pairs if not any(
            start - 0.05 <= seam.get("boundary_s", seam["start_s"]) <= end + 0.05 or
            max(start, seam["start_s"]) < min(end, seam["end_s"]) for seam in seams)]
        gap_quality = "low" if gap_quality != "unavailable" else gap_quality
    pauses = [(start, end) for start, end in pairs if (end - start) * 1000 >= pause_min_ms]
    for start, end in pauses:
        items.append(evidence(sample_id, "fluency", "pause_candidate", "measured", gap_source, gap_quality, VERSION,
                              start_s=round(start, 3), end_s=round(end, 3), value=round((end - start) * 1000), unit="ms",
                              details={"pause_min_ms": pause_min_ms, "long_pause_ms": long_pause_ms}))
    if gap_quality != "unavailable":
        durations = [(end - start) * 1000 for start, end in pauses]
        extra = {"basis": gap_source, "sample_count": len(pauses), "excluded_synthetic_seams": len(seams)}
        output.update({
            "pause_count": metric(len(pauses), "count", gap_quality, **extra),
            "long_pause_count": metric(sum(x >= long_pause_ms for x in durations), "count", gap_quality, **extra),
            "very_long_pause_count": metric(sum(x >= very_long_pause_ms for x in durations), "count", gap_quality, **extra),
            "mean_pause_ms": metric(round(mean(durations), 1) if durations else 0, "ms", gap_quality, **extra),
            "max_pause_ms": metric(round(max(durations), 1) if durations else 0, "ms", gap_quality, **extra),
        })
    else:
        for key, unit in (("pause_count", "count"), ("long_pause_count", "count"), ("very_long_pause_count", "count"), ("mean_pause_ms", "ms"), ("max_pause_ms", "ms")):
            output[key] = metric(None, unit, "unavailable", "no_reliable_pause_source")
    if usable_vad:
        span = regions["regions"][-1]["end_s"] - regions["regions"][0]["start_s"]
        speech = regions["speech_s"]
        silence = max(0, span - speech)
        output["voiced_wpm"] = metric(round(len(tokens) * 60 / speech, 2) if speech else None, "words/min", "medium", speech_s=speech)
        output["speech_silence_ratio"] = metric(round(speech / silence, 3) if silence else None, "ratio", "medium", speech_s=speech, silence_s=round(silence, 3))
        output["speech_fraction"] = metric(round(speech / span, 3) if span else None, "fraction", "medium")
    else:
        for key, unit in (("voiced_wpm", "words/min"), ("speech_silence_ratio", "ratio"), ("speech_fraction", "fraction")):
            output[key] = metric(None, unit, "unavailable", "vad_regions_unreliable")
    if len(ordered) >= max(4, int(len(tokens) * 0.8)) and trusted_window:
        phrases: list[list[dict]] = []
        current: list[dict] = []
        for token in ordered:
            if current and (token["start_s"] - current[-1]["end_s"]) * 1000 >= long_pause_ms:
                phrases.append(current)
                current = []
            current.append(token)
        if current:
            phrases.append(current)
        lengths = [phrase[-1]["end_s"] - phrase[0]["start_s"] for phrase in phrases]
        phrase_quality = "low" if not usable_vad or seams else "medium"
        output["mean_phrase_s"] = metric(round(mean(lengths), 2), "s", phrase_quality, phrase_count=len(phrases))
        output["mean_phrase_words"] = metric(round(mean(len(phrase) for phrase in phrases), 2), "words", phrase_quality, phrase_count=len(phrases))
        window_start = first
        rates = []
        while window_start + 5 <= last:
            count = sum(1 for token in ordered if window_start <= token["start_s"] < window_start + 5)
            rates.append(count * 12)
            window_start += 2.5
        output["rate_stability_cv"] = metric(round(pstdev(rates) / mean(rates), 3) if len(rates) >= 3 and mean(rates) else None,
                                              "coefficient", "medium" if len(rates) >= 3 and mean(rates) else "unavailable",
                                              None if len(rates) >= 3 and mean(rates) else "too_few_windows", window_count=len(rates))
    else:
        output["mean_phrase_s"] = metric(None, "s", "unavailable", "insufficient_word_timestamps")
        output["mean_phrase_words"] = metric(None, "words", "unavailable", "insufficient_word_timestamps")
        output["rate_stability_cv"] = metric(None, "coefficient", "unavailable", "insufficient_word_timestamps")
    for key in ("repetition_count", "false_start_count", "filler_count"):
        output[key] = metric(None, "count", "unavailable", "source_transcript_may_omit_disfluencies")
    for key, item in output.items():
        if item["value"] is not None:
            items.append(evidence(sample_id, "fluency", "metric_" + key, "measured",
                                  "webrtcvad" if key in {"voiced_wpm", "speech_silence_ratio", "speech_fraction"} else alignment["provider"],
                                  item["quality"], VERSION, start_s=None, end_s=None, value=item["value"], unit=item["unit"],
                                  details=item["details"]))
    return {"dimension": "fluency", "algorithm_version": VERSION, "status": "partial" if any(m["quality"] in {"low", "unavailable"} for m in output.values()) else "complete",
            "metrics": output, "evidence": items, "xingji_score": sample.get("fluency_score"),
            "limitations": ["Candidate pauses depend on VAD or word-gap quality; different texts can have different timing demands."] +
                           (["TTS 分段接缝附近的停顿已从候选排除；整段 WPM 仍含分段间隔。"] if seams else [])}
