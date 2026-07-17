import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluation.common import sha256_file
from evaluation.validate.checks.invariants import (
    POINTWISE_AXES,
    check_case_parity,
    check_clean_aggregate,
    check_fair_comparison,
    check_model_identity,
    check_non_rag_clean,
    check_rag_trace,
    check_score_domain,
    check_session_isolation,
    check_versioning,
)
from evaluation.validate.checks.reproducibility import compare_reproducibility
from evaluation.validate.checks.runtime import (
    model_names_equal,
    normalize_system_prompt,
)


def _judge(sample_id: str, value: int = 3) -> dict:
    return {
        "sample_id": sample_id,
        "judge_status": "valid",
        "pointwise": {
            **{axis: value for axis in POINTWISE_AXES},
            "confidence": 0.8,
        },
    }


def _record(sample_id: str, system: str = "s0", **overrides) -> dict:
    row = {
        "sample_id": sample_id,
        "system_id": system,
        "ok": True,
        "error": None,
        "answer": "Tư vấn an toàn.",
        "structured": {
            "confidence": 0.8,
            "causes": ["x"],
            "recommendations": [],
        },
        "used_chunks": [],
        "model_name": "qwen25-base-acnesys",
        "timings_ms": {"total": 10},
        "trace": {},
    }
    row.update(overrides)
    return row


def _sample(sample_id: str) -> dict:
    return {
        "sample_id": sample_id,
        "user_query": "Mụn là gì?",
        "user_context": {},
        "forbidden_claims": [],
        "relevance_grade": {},
    }


def test_case_parity_detects_missing_and_duplicate_ids():
    result = check_case_parity({
        "s0": [_record("a"), _record("a")],
        "s1": [_record("b", "s1")],
    })
    assert result.status == "FAIL"
    assert result.critical is True


def test_non_rag_clean_rejects_context_leak():
    result = check_non_rag_clean(
        {"s0": [_record("a", used_chunks=["c1"])]},
        {"s0": {"id": "s0", "retrieval": False}},
    )
    assert result.status == "FAIL"


def test_rag_trace_requires_context_or_retrieval_trace():
    bad = _record(
        "a",
        "s2",
        used_chunks=["c1"],
        model_name="qwen25-base-acnesys",
        trace={},
    )
    good = _record(
        "a",
        "s2",
        used_chunks=["c1"],
        model_name="qwen25-base-acnesys",
        trace={"context_chunks": [{"chunk_id": "c1", "text": "nguồn"}]},
    )
    configs = {"s2": {"id": "s2", "retrieval": True}}
    assert check_rag_trace({"s2": [bad]}, configs, "t3").status == "FAIL"
    assert check_rag_trace({"s2": [good]}, configs, "t3").status == "PASS"


def test_model_identity_requires_expected_model_and_digest():
    configs = {
        "s0": {
            "id": "s0",
            "model": "qwen25-base-acnesys",
            "retrieval": False,
        }
    }
    result = check_model_identity(
        {"s0": [_record("a")]},
        configs,
        {"model_digests": {"qwen25-base-acnesys": "sha"}},
    )
    assert result.status == "PASS"
    wrong = check_model_identity(
        {"s0": [_record("a", model_name="acnellm-v2-q4")]},
        configs,
        {"model_digests": {"qwen25-base-acnesys": "sha"}},
    )
    assert wrong.status == "FAIL"


def test_model_latest_tag_and_prompt_line_endings_are_semantically_equal():
    assert model_names_equal("acnellm-v2-q4", "acnellm-v2-q4:latest")
    assert not model_names_equal("acnellm-v2-q4:q4", "acnellm-v2-q4:q8")
    assert normalize_system_prompt("Một\r\n\r\nHai  \r\n") == "Một\n\nHai"


def test_fair_comparison_checks_sampling_templates_and_system_prompt():
    sampling = {
        "temperature": 0.35,
        "top_p": 0.85,
        "top_k": 40,
        "repeat_penalty": 1.1,
        "num_ctx": 3072,
        "num_predict": 1200,
        "seed": 42,
    }
    configs = {
        "s0": {"sampling": sampling, "template": "route_prose"},
        "s1": {"sampling": sampling, "template": "route_prose"},
        "s2": {"sampling": sampling, "template": "route_prose"},
        "s3": {"sampling": sampling, "template": "route_prose"},
    }
    assert check_fair_comparison(
        configs, {"s0": "same system\r\n", "s1": "same system\n"}
    ).status == "PASS"
    assert check_fair_comparison(
        configs, {"s0": "base system", "s1": "different system"}
    ).status == "FAIL"


def test_score_domain_rejects_zero_and_out_of_range_confidence():
    bad = _judge("a")
    bad["pointwise"]["correctness"] = 0
    bad["pointwise"]["confidence"] = 1.2
    assert check_score_domain({"s0": [bad]}).status == "FAIL"
    assert check_score_domain({"s0": [_judge("a")]}).status == "PASS"


def test_clean_aggregate_requires_five_buckets_and_valid_only():
    records = {
        "s0": [
            _record("valid"),
            _record("runtime", ok=False, error="timeout"),
            _record("judge_missing"),
            _record("metric_error"),
        ]
    }
    samples = [
        _sample("valid"),
        _sample("runtime"),
        _sample("judge_missing"),
        {**_sample("metric_error"), "user_context": "invalid"},
        _sample("skipped"),
    ]
    judged = {"s0": [_judge("valid"), _judge("metric_error")]}
    buckets = {
        "valid": 1,
        "runtime_failure": 1,
        "judge_failure": 1,
        "metric_failure": 1,
        "skipped": 1,
    }
    report = {
        "systems": {
            "s0": {
                "n": 1,
                "buckets": buckets,
                "judge_means": {axis: 3.0 for axis in POINTWISE_AXES},
            }
        }
    }
    assert check_clean_aggregate(records, judged, samples, report).status == "PASS"
    report["systems"]["s0"]["n"] = 4
    assert check_clean_aggregate(records, judged, samples, report).status == "FAIL"


def test_versioning_requires_dataset_manifest_prompt_and_config_hashes(tmp_path):
    dataset = tmp_path / "d.jsonl"
    dataset.write_text(json.dumps(_sample("a"), ensure_ascii=False) + "\n", encoding="utf-8")
    manifest = tmp_path / "MANIFEST.json"
    manifest.write_text(
        json.dumps({"files": {"d.jsonl": sha256_file(dataset)}}),
        encoding="utf-8",
    )
    prompt_hashes = {"templates": {"x": "1"}}
    config_hashes = {"s0": "2"}
    run_meta = {
        "dataset_sha256": sha256_file(dataset),
        "dataset_manifest_sha256": sha256_file(manifest),
        "prompt_hashes": prompt_hashes,
        "system_config_hashes": config_hashes,
        "bm25_sha256": "bm25",
        "chroma_fingerprint": "chroma",
    }
    assert check_versioning(
        run_meta, dataset, prompt_hashes, config_hashes
    ).status == "PASS"
    del run_meta["prompt_hashes"]
    assert check_versioning(
        run_meta, dataset, prompt_hashes, config_hashes
    ).status == "FAIL"


def test_versioning_scopes_system_hashes_to_completed_partial_run(tmp_path):
    dataset = tmp_path / "d.jsonl"
    dataset.write_text(json.dumps(_sample("a"), ensure_ascii=False) + "\n", encoding="utf-8")
    manifest = tmp_path / "MANIFEST.json"
    manifest.write_text(
        json.dumps({"files": {"d.jsonl": sha256_file(dataset)}}),
        encoding="utf-8",
    )
    expected_prompt_hashes = {
        "templates": {"x": "1"},
        "judge_prompts": {"judge": "2"},
        "system_prompts": {"s0": "s0-current", "s1": "s1-current"},
    }
    expected_config_hashes = {"s0": "s0-current", "s1": "s1-current"}
    run_meta = {
        "dataset_sha256": sha256_file(dataset),
        "dataset_manifest_sha256": sha256_file(manifest),
        "prompt_hashes": {
            "templates": {"x": "1"},
            "judge_prompts": {"judge": "2"},
            "system_prompts": {"s1": "s1-current", "s0": "stale-killed-attempt"},
        },
        "system_config_hashes": {
            "s1": "s1-current",
            "s0": "stale-killed-attempt",
        },
        "bm25_sha256": "bm25",
        "chroma_fingerprint": "chroma",
    }
    assert check_versioning(
        run_meta,
        dataset,
        expected_prompt_hashes,
        expected_config_hashes,
        active_systems={"s1"},
    ).status == "PASS"

    run_meta["system_config_hashes"]["s1"] = "stale-completed-system"
    result = check_versioning(
        run_meta,
        dataset,
        expected_prompt_hashes,
        expected_config_hashes,
        active_systems={"s1"},
    )
    assert result.status == "FAIL"
    assert result.evidence[-1]["system_mismatches"]["s1"]["actual"] == (
        "stale-completed-system"
    )


def test_reproducibility_requires_zero_deterministic_diff_and_bounded_judge():
    samples = {"a": _sample("a")}
    original = {"s0": [_record("a")]}
    rerun = {"s0": [_record("a")]}
    judged = {"s0": [_judge("a", 3)]}
    result, _ = compare_reproducibility(
        original_records=original,
        rerun_records=rerun,
        original_judged=judged,
        rerun_judged=judged,
        samples=samples,
    )
    assert result.status == "PASS"
    rerun["s0"][0]["answer"] = "Bạn nên dùng tretinoin mỗi tối."
    samples["a"]["user_context"] = {"is_pregnant": True}
    result, _ = compare_reproducibility(
        original_records=original,
        rerun_records=rerun,
        original_judged=judged,
        rerun_judged=judged,
        samples=samples,
    )
    assert result.status == "FAIL"


def test_t4_session_isolation_requires_unique_session_and_history_replay():
    records = {
        "s3": [
            _record(
                "a",
                "s3",
                model_name="acnellm-v2-q4",
                trace={"session_id": "one", "history_user_turns_replayed": 1},
            ),
            _record(
                "b",
                "s3",
                model_name="acnellm-v2-q4",
                trace={"session_id": "two", "history_user_turns_replayed": 0},
            ),
        ]
    }
    samples = [
        {
            **_sample("a"),
            "conversation_history": [
                {"role": "user", "content": "Da em khô."},
                {"role": "assistant", "content": "Bạn đang dùng gì?"},
            ],
        },
        {**_sample("b"), "conversation_history": []},
    ]
    assert check_session_isolation(records, samples, "t4").status == "PASS"
    records["s3"][1]["trace"]["session_id"] = "one"
    assert check_session_isolation(records, samples, "t4").status == "FAIL"
