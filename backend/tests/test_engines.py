from app.engines.fluency import analyze_fluency
from app.engines.pronunciation import analyze_pronunciation


def sample():
    return {"tokens": [
        {"index": 0, "surface": "The", "normalized": "the", "color": "red", "color_review_status": "confirmed", "color_source_screenshot_id": "image_1"},
        {"index": 1, "surface": "chart", "normalized": "chart", "color": "yellow", "color_review_status": "confirmed", "color_source_screenshot_id": "image_1"},
        {"index": 2, "surface": "rises", "normalized": "rises", "color": "unknown", "color_review_status": "unreviewed", "color_source_screenshot_id": None},
    ], "pronunciation_score": {"value": 70, "max": 90}, "fluency_score": {"value": 75, "max": 90}}


def alignment():
    return {"provider": "test-aligner", "tokens": [
        {"index": 0, "start_s": 0.5, "end_s": 0.8, "quality": "medium"},
        {"index": 1, "start_s": 1.4, "end_s": 1.8, "quality": "medium"},
        {"index": 2, "start_s": 2.0, "end_s": 2.5, "quality": "medium"},
    ]}


def test_pronunciation_runs_alone_and_ignores_unreviewed_color():
    result = analyze_pronunciation("sample_1", sample(), alignment())
    assert result["summary"]["known_count"] == 2
    assert result["summary"]["unknown_count"] == 1
    assert [target["color"] for target in result["targets"]] == ["red", "yellow"]
    assert result["targets"][0]["start_s"] == 0.5
    assert all(item["source_type"] == "external" for item in result["evidence"])


def test_fluency_runs_alone_and_degrades_unreliable_vad():
    audio = {"speech_regions": {"quality": "low", "regions": [{"start_s": 0.5, "end_s": 2.6}], "speech_s": 2.1}}
    result = analyze_fluency("sample_1", sample(), audio, alignment())
    assert result["metrics"]["wpm"]["value"] == 90
    assert result["metrics"]["pause_count"]["value"] == 1
    assert result["metrics"]["pause_count"]["quality"] == "low"
    assert result["metrics"]["speech_silence_ratio"]["value"] is None
    assert result["metrics"]["filler_count"]["value"] is None
    assert result["status"] == "partial"


def test_missing_alignment_never_invents_word_times_or_wpm():
    unavailable = {"provider": "none", "tokens": []}
    audio = {"speech_regions": {"quality": "low", "regions": [], "speech_s": 0}}
    pronunciation = analyze_pronunciation("sample_1", sample(), unavailable)
    fluency = analyze_fluency("sample_1", sample(), audio, unavailable)
    assert pronunciation["targets"][0]["start_s"] is None
    assert fluency["metrics"]["wpm"]["value"] is None
    assert fluency["metrics"]["pause_count"]["value"] is None


def test_reliable_vad_retains_audio_level_metrics_without_word_alignment():
    unavailable = {"provider": "none", "tokens": []}
    audio = {"speech_regions": {"quality": "medium", "regions": [
        {"start_s": 1.0, "end_s": 2.0}, {"start_s": 2.7, "end_s": 3.7}], "speech_s": 2.0}}
    result = analyze_fluency("sample_1", sample(), audio, unavailable)
    assert result["metrics"]["wpm"]["value"] == 66.67
    assert result["metrics"]["wpm"]["details"]["basis"] == "vad_speech_span"
    assert result["metrics"]["pause_count"]["value"] == 1
    assert result["metrics"]["mean_phrase_words"]["value"] is None
    assert result["metrics"]["rate_stability_cv"]["value"] is None


def test_phrase_length_excludes_the_pause_itself():
    with_more_words = sample()
    with_more_words["tokens"].append({"index": 3, "surface": "steadily", "normalized": "steadily", "color": "unknown", "color_review_status": "unreviewed"})
    timed = alignment()
    timed["tokens"].append({"index": 3, "start_s": 2.6, "end_s": 2.9, "quality": "medium"})
    audio = {"speech_regions": {"quality": "low", "regions": [], "speech_s": 0}}
    result = analyze_fluency("sample_1", with_more_words, audio, timed)
    assert result["metrics"]["mean_phrase_words"]["value"] == 2
    assert result["metrics"]["mean_phrase_s"]["value"] == 0.9
