"""总结必须来自本次指标与证据，模型越界时保留本机版本。"""
from app.engines.report_summaries import build_summaries


def _inputs():
    # 模拟两侧词速可用、停顿质量低、用户侧 VAD 不可靠的真实组合。
    def metric(value, quality="medium", reason=None):
        return {"value": value, "quality": quality, "reason": reason, "unit": "count", "details": {}}
    comparison = {"fluency_metric_differences": {
        "wpm": {"user": metric(158.28), "benchmark": metric(171.66), "delta_user_minus_benchmark": -13.38, "quality": "medium"},
        "long_pause_count": {"user": metric(5, "low"), "benchmark": metric(4, "low"), "delta_user_minus_benchmark": 1, "quality": "low"},
        "speech_fraction": {"user": metric(None, "unavailable", "vad_regions_unreliable"), "benchmark": metric(0.9), "delta_user_minus_benchmark": None, "quality": "unavailable"}}}
    diagnosis = {"findings": [{"id": "finding_1", "kind": "red_word_practice", "statement": "有红词", "recommendation": "回听", "evidence_ids": ["red_1"], "limitations": []}]}
    pronunciation = {"evidence": [{"id": "red_1", "kind": "xingji_word_color", "start_s": 12.5, "quality": "high", "details": {"color": "red", "surface": "buy", "review_status": "confirmed"}}]}
    fluency = {"evidence": [{"id": "pause_1", "kind": "pause_candidate", "start_s": 18.2, "value": 560, "quality": "low"}]}
    return comparison, diagnosis, pronunciation, fluency


def test_local_summary_names_this_recording_and_limits_uncertain_pauses():
    result = build_summaries(*_inputs())
    assert "158.28" in result["fluency"]["text"]
    assert "质量低" in result["fluency"]["text"]
    assert "语音与静音" in result["fluency"]["text"]
    assert "buy（12.50 秒）" in result["practice"]["text"]
    assert "18.20 秒" in result["practice"]["text"]
    assert set(result["practice"]["evidence_ids"]) == {"red_1", "pause_1"}


def test_invalid_ai_summary_cannot_invent_a_numeric_claim():
    class InventingModel:
        def summarize_report(self, metrics, findings, facts, fluency_baseline, practice_baseline):
            return {"fluency": {"text": "你需要提高到 200 WPM。", "metric_keys": ["wpm"]},
                    "practice": {"text": "回听 buy。", "finding_ids": ["finding_1"]}}

    result = build_summaries(*_inputs(), InventingModel())
    assert result["fluency"]["source"] == "local_rules"
    assert result["practice"]["source"] == "local_rules"
    assert result["fallback_reason"] == "ai_unavailable_or_invalid"


def test_ai_connection_failure_preserves_local_word_and_timing_examples():
    class OfflineModel:
        def summarize_report(self, *args):
            raise ConnectionError("proxy unavailable")

    result = build_summaries(*_inputs(), OfflineModel())
    assert result["practice"]["source"] == "local_rules"
    assert "buy（12.50 秒）" in result["practice"]["text"]
    assert "18.20 秒" in result["practice"]["text"]
