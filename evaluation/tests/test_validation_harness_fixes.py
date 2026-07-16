import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluation.adapters.sse_api import SseApiAdapter
from evaluation.analysis import report as report_module
from evaluation.analysis.check_gate import (
    _normalizer_micro_f1,
    _select_primary_retrieval_summary,
)
from evaluation import run_all
from evaluation.runners.run_experiment import merge_run_meta, validate_output_state
from evaluation.validate.checks.invariants import POINTWISE_AXES


def _dataset_row(sample_id: str) -> dict:
    return {
        "sample_id": sample_id,
        "user_query": "Mụn viêm nên chăm sóc thế nào?",
        "task_type": "advise",
        "split": "test",
        "dataset_version": "v1.0",
        "source_provenance": "human_written",
        "user_context": {},
        "expected_answer_points": [],
        "forbidden_claims": [],
    }


def _judge_row(sample_id: str) -> dict:
    return {
        "sample_id": sample_id,
        "system_id": "s0",
        "judge_status": "valid",
        "pointwise": {
            **{axis: 3 for axis in POINTWISE_AXES},
            "confidence": 0.8,
        },
    }


def test_sse_adapter_uses_unique_session_same_history_session_and_condition_mode():
    adapter = SseApiAdapter(
        {
            "id": "s0",
            "model": "qwen25-base-acnesys",
            "retrieval": False,
            "adapter": "ollama_batch",
        },
        {"api_url": "http://localhost:8000", "chat_mode": "auto"},
    )
    calls = []

    def fake_request(message: str, session_id: str, mode: str):
        calls.append((message, session_id, mode))
        return {
            "answer": f"answer:{message}",
            "used_chunks": [],
            "mode": mode,
            "latency_ms": 10,
            "session_id": session_id,
            "primary_intent": "advise",
            "query_subject": "self",
            "route_flags": [],
            "citations": [],
            "errors": [],
        }

    adapter._request_payload = fake_request  # type: ignore[method-assign]
    output = adapter.generate(
        {
            "sample_id": "d5-0001",
            "user_query": "Giờ da khô căng thì sao?",
            "conversation_history": [
                {"role": "user", "content": "Em đã đổi sữa rửa mặt."},
                {"role": "assistant", "content": "Hãy theo dõi kích ứng."},
            ],
        },
        None,
    )
    assert output["answer"] == "answer:Giờ da khô căng thì sao?"
    assert len(calls) == 2
    assert calls[0][1] == calls[1][1]
    assert all(call[2] == "llm_only" for call in calls)
    assert adapter.collect_trace()["history_user_turns_replayed"] == 1
    assert adapter.collect_trace()["session_id"] == calls[0][1]


def test_report_excludes_runtime_and_judge_failures_and_writes_buckets(
    tmp_path, monkeypatch
):
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text(
        "\n".join(
            json.dumps(_dataset_row(sample_id), ensure_ascii=False)
            for sample_id in ("valid", "runtime", "judge_missing", "skipped")
        )
        + "\n",
        encoding="utf-8",
    )
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    results = [
        {
            "sample_id": "valid",
            "system_id": "s0",
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
            "timings_ms": {"total": 12},
            "trace": {},
        },
        {
            "sample_id": "runtime",
            "system_id": "s0",
            "ok": False,
            "error": "timeout",
            "answer": "",
            "structured": None,
            "used_chunks": [],
            "model_name": None,
            "timings_ms": {"total": 1},
            "trace": {},
        },
        {
            "sample_id": "judge_missing",
            "system_id": "s0",
            "ok": True,
            "error": None,
            "answer": "Không có judge.",
            "structured": {
                "confidence": 0.8,
                "causes": ["x"],
                "recommendations": [],
            },
            "used_chunks": [],
            "model_name": "qwen25-base-acnesys",
            "timings_ms": {"total": 8},
            "trace": {},
        },
    ]
    (run_dir / "s0.results.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in results) + "\n",
        encoding="utf-8",
    )
    (run_dir / "s0.judged.jsonl").write_text(
        json.dumps(_judge_row("valid"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "report",
            "--run-dir",
            str(run_dir),
            "--dataset",
            str(dataset),
        ],
    )
    report_module.main()
    report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    system = report["systems"]["s0"]
    assert system["n"] == 1
    assert system["buckets"] == {
        "valid": 1,
        "runtime_failure": 1,
        "judge_failure": 1,
        "metric_failure": 0,
        "skipped": 1,
    }
    assert system["judge_means"]["correctness"] == 3.0


def test_gate_prefers_primary_retrieval_and_reads_strict_normalizer(tmp_path):
    primary = tmp_path / "2026-01-01" / "summary.json"
    ablation = tmp_path / "2026-01-02" / "summary.json"
    primary.parent.mkdir()
    ablation.parent.mkdir()
    primary.write_text(json.dumps({"raw_query": False}), encoding="utf-8")
    ablation.write_text(json.dumps({"raw_query": True}), encoding="utf-8")
    assert _select_primary_retrieval_summary([primary, ablation]) == primary
    assert _normalizer_micro_f1({
        "multi_label": {
            "lesion_strict": {"micro_f1": 0.75},
            "lesion_bucket": {"micro_f1": 0.865},
        }
    }) == 0.75


def test_run_all_executes_gate_step(tmp_path, monkeypatch):
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text("{}\n", encoding="utf-8")
    run_dir = tmp_path / "reports" / "main_2x2_t3"
    run_dir.mkdir(parents=True)
    config = {
        "name": "main_2x2_t3",
        "dataset": str(dataset),
        "systems": [],
        "comparisons": [],
    }
    calls: list[tuple[str, list[str]]] = []

    monkeypatch.setattr(run_all, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(run_all, "load_yaml", lambda _path: dict(config))
    monkeypatch.setattr(run_all, "preflight", lambda _cfg, _skip: [])

    def fake_sh(step: str, command: list[str], results: dict) -> bool:
        calls.append((step, command))
        results[step] = "OK"
        return True

    monkeypatch.setattr(run_all, "sh", fake_sh)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_all",
            "--skip",
            "t1,t2,t3,judge,report",
            "--dataset",
            str(dataset),
        ],
    )
    run_all.main()
    gate_calls = [command for step, command in calls if step == "gate"]
    assert len(gate_calls) == 1
    assert gate_calls[0][-2:] == ["--run-dir", str(run_dir)]


def _resume_state(system_hash: str = "hash-s1") -> dict:
    return {
        "dataset": "evaluation/datasets/v1/d2_test.jsonl",
        "dataset_sha256": "dataset-hash",
        "experiment_config_sha256": "experiment-hash",
        "system_config_hashes": {"s1": system_hash},
    }


def test_run_experiment_rejects_existing_results_without_resume(tmp_path):
    (tmp_path / "s1.results.jsonl").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="already contains results"):
        validate_output_state(tmp_path, False, _resume_state())


def test_run_experiment_rejects_resume_metadata_mismatch(tmp_path):
    (tmp_path / "s1.results.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / "run_meta.json").write_text(
        json.dumps({**_resume_state(), "dataset_sha256": "old-dataset"}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="dataset_sha256"):
        validate_output_state(tmp_path, True, _resume_state())


def test_run_experiment_allows_compatible_new_system_and_merges_metadata(tmp_path):
    existing = {
        **_resume_state(),
        "systems": ["s1"],
        "model_digests": {"fine": "digest-1"},
        "prompt_hashes": {
            "templates": {"shared": "template-hash"},
            "judge_prompts": {},
            "system_prompts": {"s1": "prompt-1"},
        },
    }
    (tmp_path / "s1.results.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / "run_meta.json").write_text(
        json.dumps(existing),
        encoding="utf-8",
    )
    expected_s0 = {
        **_resume_state(),
        "system_config_hashes": {"s0": "hash-s0"},
    }
    loaded = validate_output_state(tmp_path, True, expected_s0)
    merged = merge_run_meta(
        loaded,
        {
            **expected_s0,
            "systems": ["s0"],
            "model_digests": {"base": "digest-0"},
            "prompt_hashes": {
                "templates": {"shared": "template-hash"},
                "judge_prompts": {},
                "system_prompts": {"s0": "prompt-0"},
            },
        },
    )
    assert merged["systems"] == ["s0", "s1"]
    assert merged["system_config_hashes"] == {
        "s0": "hash-s0",
        "s1": "hash-s1",
    }
    assert merged["prompt_hashes"]["system_prompts"] == {
        "s0": "prompt-0",
        "s1": "prompt-1",
    }
