"""Single-machine analysis run bound to immutable sample revisions."""
import json
import time
from pathlib import Path

from app.audio.alignment import NoAlignment, create_alignment_provider, tts_word_boundaries
from app.audio.acoustics import extract_bounded
from app.audio.prepare import prepare_audio
from app.comparison.service import compare
from app.config import Settings
from app.engines.diagnosis import diagnose
from app.engines.common import plain
from app.engines.fluency import analyze_fluency
from app.engines.pronunciation import analyze_pronunciation
from app.engines.report_summaries import build_summaries
from app.persistence.database import connect
from app.persistence.samples import now, uid
from app.providers.openai_llm import OpenAILLMProvider, OpenAICompatibleLLMProvider
from app.providers.openpronounce import OpenPronouncePhones

VERSION = "analysis-v5"


def _snapshot(db, sample_id: str) -> tuple[str, dict]:
    row = db.execute("SELECT input_version FROM response_samples WHERE id=?", (sample_id,)).fetchone()
    revision = db.execute("SELECT id,payload_json FROM sample_revisions WHERE sample_id=? AND version=?",
                          (sample_id, row["input_version"])).fetchone()
    return revision["id"], json.loads(revision["payload_json"])


def _prepare_one(sample_id: str, sample: dict, settings: Settings, pronunciation_provider) -> dict:
    if not sample.get("audio_asset_id") or not sample.get("transcript_raw"):
        raise ValueError("audio_and_transcript_required_for_analysis")
    started = time.perf_counter()
    audio = prepare_audio(sample["audio_asset_id"], settings)
    wav_path = settings.data_dir / audio["wav_path"]
    alignment_error = None
    if sample.get("audio_origin") == "edge_tts":
        with connect(settings.database_path) as db:
            source = db.execute("SELECT word_boundaries_json,seam_intervals_json,voice,rate FROM tts_generations WHERE audio_asset_id=?",
                                (sample["audio_asset_id"],)).fetchone()
        if not source:
            raise ValueError("tts_generation_not_found")
        audio["tts"] = {"voice": source["voice"], "rate": source["rate"],
                        "seam_intervals": json.loads(source["seam_intervals_json"])}
        alignment = tts_word_boundaries(sample["tokens"], json.loads(source["word_boundaries_json"]), audio["duration_s"])
    else:
        try:
            provider = create_alignment_provider(settings.alignment_provider, settings.data_dir)
            alignment = provider.align(wav_path, sample["tokens"], audio["duration_s"])
        except Exception as exc:
            alignment_error = type(exc).__name__
            alignment = NoAlignment().align(wav_path, sample["tokens"], audio["duration_s"])
            alignment["reason"] = "alignment_failed"
    pronunciation = analyze_pronunciation(sample_id, sample, alignment, wav_path, pronunciation_provider)
    fluency = analyze_fluency(sample_id, sample, audio, alignment,
                              settings.pause_min_ms, settings.long_pause_ms, settings.very_long_pause_ms)
    # 曲线是可选展示数据：超时或失败会局部降级，不能改变发音/流利度证据。
    acoustic = extract_bounded(wav_path)
    return {"sample_id": sample_id, "sample": sample, "audio": audio, "alignment": alignment,
            "pronunciation": pronunciation, "fluency": fluency, "acoustic": acoustic,
            "alignment_error": alignment_error,
            "elapsed_s": round(time.perf_counter() - started, 3)}


def run_comparison(comparison_id: str, settings: Settings, allow_cloud: bool = False,
                   use_openpronounce: bool = False) -> dict:
    llm = None
    cloud_ready = bool(settings.openai_api_key.get_secret_value().strip() and settings.openai_analysis_model.strip())
    if allow_cloud and cloud_ready:
        if settings.llm_provider == "openai":
            llm = OpenAILLMProvider(settings.openai_api_key.get_secret_value(), settings.openai_analysis_model)
        elif settings.llm_provider == "openai_compatible":
            llm = OpenAICompatibleLLMProvider(settings.openai_api_key.get_secret_value(),
                                             settings.openai_analysis_model, settings.openai_base_url)
        else:
            raise ValueError("llm_provider_not_supported")
    with connect(settings.database_path) as db:
        db.execute("BEGIN IMMEDIATE")
        comparison = db.execute("SELECT c.user_sample_id,c.benchmark_sample_id,e.reading_text_raw FROM comparisons c JOIN exercises e ON e.id=c.exercise_id WHERE c.id=?", (comparison_id,)).fetchone()
        if not comparison:
            raise ValueError("comparison_not_found")
        active = db.execute("SELECT 1 FROM analysis_runs WHERE comparison_id=? AND status='running'", (comparison_id,)).fetchone()
        if active:
            raise ValueError("analysis_already_running")
        ids = {"user": comparison["user_sample_id"], "benchmark": comparison["benchmark_sample_id"]}
        snapshots = {role: _snapshot(db, sample_id) for role, sample_id in ids.items()}
        reading_text_raw = comparison["reading_text_raw"]
        run_id = uid("run")
        config = {"alignment_provider": settings.alignment_provider, "pronunciation_provider": "openpronounce" if use_openpronounce else "none",
                  "llm_requested": allow_cloud, "llm_provider": settings.llm_provider if llm else "none",
                  "llm_model": settings.openai_analysis_model if llm else None,
                  "pause_min_ms": settings.pause_min_ms,
                  "long_pause_ms": settings.long_pause_ms, "very_long_pause_ms": settings.very_long_pause_ms,
                  "cross_dimension_window_ms": settings.cross_dimension_window_ms}
        db.execute("INSERT INTO analysis_runs VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                   (run_id, comparison_id, snapshots["user"][0], snapshots["benchmark"][0], "running", VERSION,
                    json.dumps(config), json.dumps({}), None, now(), None))
    try:
        phoneme_provider = OpenPronouncePhones() if use_openpronounce else None
        results = {role: _prepare_one(ids[role], snapshots[role][1], settings, phoneme_provider) for role in ("user", "benchmark")}
        left, right = results["user"], results["benchmark"]
        comparison_result = compare(left["sample"], right["sample"], left["alignment"], right["alignment"],
                                    left["pronunciation"], right["pronunciation"], left["fluency"], right["fluency"],
                                    reading_text_raw)
        diagnosis = diagnose(left["pronunciation"], left["fluency"], comparison_result, llm, settings.cross_dimension_window_ms)
        # 本机先生成可追溯总结；已授权 AI 时再尝试改写，失效会回退。
        summaries = build_summaries(comparison_result, diagnosis, left["pronunciation"], left["fluency"], llm)
        partial = any(result["alignment"]["status"] != "complete" or result["fluency"]["status"] != "complete" or result["pronunciation"]["status"] != "complete" for result in results.values())
        report = {"run_id": run_id, "comparison_id": comparison_id, "status": "partial" if partial else "complete",
                  "pipeline_version": VERSION, "config": config,
                  "revision_ids": {role: snapshots[role][0] for role in snapshots},
                  "samples": results, "comparison": comparison_result, "diagnosis": diagnosis, "summaries": summaries,
                  "limitations": ["TTS audio is an online-generated practice reference without Xingji scoring." if right["sample"].get("audio_origin") == "edge_tts" else "Benchmark is not a standard answer or official scoring reference.",
                                  "Content scores are stored Xingji inputs; no content scoring is performed."]}
        report = plain(report)
        with connect(settings.database_path) as db:
            for role, result in results.items():
                sample_id = ids[role]
                for token in result["alignment"]["tokens"]:
                    db.execute("INSERT INTO timed_tokens VALUES (?,?,?,?,?,?,?)",
                               (run_id, sample_id, token["index"], token.get("start_s"), token.get("end_s"),
                                token["quality"], result["alignment"]["provider"]))
                for key, value in result["fluency"]["metrics"].items():
                    db.execute("INSERT INTO metrics VALUES (?,?,?,?,?,?,?,?)",
                               (run_id, sample_id, "fluency", key, value["value"], value["unit"], value["quality"], json.dumps(value)))
                summary = result["pronunciation"]["summary"]
                for color, count in summary["counts"].items():
                    db.execute("INSERT INTO metrics VALUES (?,?,?,?,?,?,?,?)",
                               (run_id, sample_id, "pronunciation", color + "_count", count, "count", "high", json.dumps({"known_count": summary["known_count"]})))
                for item in result["pronunciation"]["evidence"] + result["fluency"]["evidence"]:
                    db.execute("INSERT INTO evidence VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                               (item["id"], run_id, sample_id, item["dimension"], item["kind"], item.get("token_index"),
                                item.get("start_s"), item.get("end_s"), item.get("value"), item.get("unit"),
                                item["source_type"], item["source_ref"], item["quality"], item["algorithm_version"], json.dumps(item.get("details", {}))))
            for finding in diagnosis["findings"]:
                db.execute("INSERT INTO findings VALUES (?,?,?,?,?,?,?,?,?)",
                           (finding["id"], run_id, finding["kind"], finding["severity"], finding["confidence_level"],
                            finding["statement"], json.dumps(finding["limitations"]), json.dumps({"text": finding["recommendation"]}), finding["rule_version"]))
                for evidence_id in finding["evidence_ids"]:
                    db.execute("INSERT INTO finding_evidence VALUES (?,?)", (finding["id"], evidence_id))
            db.execute("INSERT INTO comparisons_result VALUES (?,?)", (run_id, json.dumps(report)))
            db.execute("UPDATE analysis_runs SET status=?,provider_versions_json=?,finished_at=? WHERE id=?",
                       (report["status"], json.dumps({"alignment": left["alignment"]["provider"],
                                                     "pronunciation": left["pronunciation"]["provider"],
                                                     "llm": diagnosis["llm_status"]}), now(), run_id))
        return {"run_id": run_id, "status": report["status"], "completed_steps": ["pronunciation", "fluency", "comparison", "diagnosis", "summaries"],
                "degraded_reasons": [f"{role}_{results[role]['alignment']['reason']}" for role in results if results[role]["alignment"].get("reason")]}
    except Exception as exc:
        with connect(settings.database_path) as db:
            db.execute("UPDATE analysis_runs SET status='failed',error_json=?,finished_at=? WHERE id=?",
                       (json.dumps({"code": type(exc).__name__}), now(), run_id))
        raise
