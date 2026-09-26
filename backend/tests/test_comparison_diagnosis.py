from app.comparison.service import _pair_indices, shared_pairs
from app.engines.diagnosis import diagnose
from app.engines.fluency import analyze_fluency
from app.engines.pronunciation import analyze_pronunciation
from test_engines import alignment, sample


def test_shared_words_only_and_repeated_instances_are_unique():
    user = sample()
    benchmark = sample()
    user["tokens"].append({"index": 3, "surface": "chart", "normalized": "chart", "color": "red", "color_review_status": "confirmed", "color_source_screenshot_id": "image_1"})
    benchmark["tokens"][2].update(surface="falls", normalized="falls")
    left = analyze_pronunciation("u", user, alignment())
    right = analyze_pronunciation("b", benchmark, alignment())
    pairs = shared_pairs(user, benchmark, alignment(), alignment(), left, right)
    assert [pair["word"] for pair in pairs] == ["the", "chart"]
    assert len({pair["user_index"] for pair in pairs}) == len(pairs)
    assert all(pair["word"] != "falls" for pair in pairs)


def test_shared_script_pairs_occurrences_and_reports_tail_without_attribution():
    def observed(words):
        return {"tokens": [{"normalized": word} for word in words.split()]}

    pairs, summary = _pair_indices(observed("the chart rises"), observed("the chart rises then falls"),
                                   "the chart rises then falls")
    assert pairs == [(0, 0), (1, 1), (2, 2)]
    assert summary["user_script_tail_unobserved"] == 2
    assert summary["benchmark_script_tail_unobserved"] == 0
    assert "pronunciation" in summary["limitation"]

    pairs, summary = _pair_indices(observed("the red the line"), observed("the blue the line"),
                                   "the red the line")
    assert pairs == [(0, 0), (2, 2), (3, 3)]
    assert summary["user_unmatched_transcript_words"] == 0
    assert summary["benchmark_unmatched_transcript_words"] == 1


def test_diagnosis_rejects_invented_evidence_and_falls_back():
    user = sample()
    pron = analyze_pronunciation("u", user, alignment())
    audio = {"speech_regions": {"quality": "low", "regions": [{"start_s": 0.5, "end_s": 2.6}], "speech_s": 2.1}}
    flu = analyze_fluency("u", user, audio, alignment())
    comparison = {"fluency_metric_differences": {}}

    class InventingProvider:
        def explain(self, findings, evidence):
            return [{"id": findings[0]["id"], "evidence_ids": ["invented"],
                     "statement": "unsupported", "recommendation": "unsupported"}]

    result = diagnose(pron, flu, comparison, InventingProvider())
    assert result["llm_status"] == "fallback_to_rules"
    assert result["findings"][0]["kind"] == "red_word_practice"
    assert result["findings"][0]["statement"] != "unsupported"
    existing = {item["id"] for item in pron["evidence"] + flu["evidence"]}
    assert all(id in existing for finding in result["findings"] for id in finding["evidence_ids"])


def test_diagnosis_does_not_apply_partial_llm_edits_on_validation_failure():
    pronunciation = {"evidence": [{"id": "red", "kind": "xingji_word_color", "details": {"color": "red"},
                                   "start_s": None, "end_s": None}]}
    fluency = {"evidence": [{"id": "pause", "kind": "pause_candidate", "quality": "medium", "value": 700}],
               "metrics": {"long_pause_count": {"value": 1, "quality": "medium"}}}

    class InvalidSecondFinding:
        def explain(self, findings, evidence):
            return [{"id": findings[0]["id"], "evidence_ids": findings[0]["evidence_ids"],
                     "statement": "overwritten", "recommendation": "overwritten"},
                    {"id": findings[1]["id"], "evidence_ids": ["invented"],
                     "statement": "overwritten", "recommendation": "overwritten"}]

    result = diagnose(pronunciation, fluency, {"fluency_metric_differences": {}}, InvalidSecondFinding())
    assert result["llm_status"] == "fallback_to_rules"
    assert len(result["findings"]) == 2
    assert all(finding["statement"] != "overwritten" for finding in result["findings"])
