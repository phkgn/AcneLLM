from __future__ import annotations

import asyncio
from collections import Counter
import json
from pathlib import Path

import pytest

import evaluation.datasets.make_intake_set_v2 as v2
from datagen.intakedata.config import Config
from datagen.intakedata.gates import CorpusGateState
from datagen.intakedata.anchor import load_anchor


ANCHOR = load_anchor(Config(api_key="test"))


def _case(name: str) -> v2.Case:
    return next(case for case in v2.CASES if case.name == name)


def _payload(user: str, *, lesion: str = "cyst") -> dict:
    return {
        "intent": "advise",
        "confidence": 0.96,
        "description": user,
        "context": {
            "age": None,
            "sex": None,
            "skin_type": None,
            "is_pregnant": None,
            "is_breastfeeding": None,
            "duration_weeks": None,
            "allergies": [],
            "current_products": [],
            "medications": [],
        },
        "clinical": {
            "lesion_types": [{"value": lesion, "confidence": 0.95}],
            "inflammation_level": {"value": "severe", "confidence": 0.9},
            "lesion_distribution": [{"value": "chin", "confidence": 0.9}],
        },
    }


def _record(user: str, *, record_id: str = "r1", content: str | None = None) -> dict:
    return {
        "id": record_id,
        "messages": [
            {"role": "system", "content": ANCHOR},
            {"role": "user", "content": user},
            {
                "role": "assistant",
                "content": content if content is not None else json.dumps(_payload(user)),
            },
        ],
        "meta": {
            "case_type": "advise_selfreport_simple",
            "source": "intake_eval_v2:test",
            "seed": {"required_user_cues": [user]},
            "eval_case": "lesion_cyst",
        },
    }


class FakeSemantic:
    def __init__(self, scores: list[float]):
        self.scores = list(scores)
        self.calls = 0
        self.accepts = 0
        self.dedup_threshold = 0.90

    def score(self, query: str) -> v2.EvalScore:
        self.calls += 1
        return v2.EvalScore([float(self.calls)], self.scores.pop(0))

    def accept(self, vector) -> None:
        self.accepts += 1


def test_manifest_is_exactly_1500_and_excludes_undefined_other_values():
    assert v2.TOTAL == 1_500
    assert len(v2.CASES) == 67
    assert len(set(case.name for case in v2.CASES)) == len(v2.CASES)
    assert "other" not in v2.LESION_CUES
    assert "other" not in v2.DISTRIBUTION_CUES

    fixed = sum(case.quota for case in v2.CASES if case.expectation.kind == "exact")
    opened = v2.TOTAL - fixed
    assert fixed == 1_290
    assert opened == 210

    by_intent = Counter()
    for case in v2.CASES:
        if case.path == "intent":
            by_intent[case.expectation.value] += case.quota
    assert by_intent == Counter(advise=30, knowledge=30, clarify=30, reject=30)


def test_open_field_buckets_and_positive_negative_lists_are_explicit():
    age = [case for case in v2.CASES if case.path == "context.age"]
    duration = [case for case in v2.CASES if case.path == "context.duration_weeks"]
    assert [(c.expectation.minimum, c.expectation.maximum, c.quota) for c in age] == [
        (0, 0, 10), (1, 11, 10), (12, 17, 10),
        (18, 24, 10), (25, 39, 10), (40, None, 10),
    ]
    assert [(c.expectation.minimum, c.expectation.maximum, c.quota) for c in duration] == [
        (0, 0, 10), (1, 4, 10), (5, 12, 10),
        (13, 26, 10), (27, 52, 10), (53, None, 10),
    ]
    for field in ("allergies", "current_products", "medications"):
        present = _case(f"{field}_present")
        negative = _case(f"{field}_negative")
        assert (present.quota, present.expectation.kind) == (15, "nonempty")
        assert (negative.quota, negative.expectation.kind) == (15, "empty")


def test_seed_for_unknown_inflammation_has_location_but_no_invented_lesion():
    seed = v2.seed_for_case(_case("inflammation_unknown"), v2.random.Random(1))
    assert seed["distribution"] == "chin"
    assert seed["inflammation_level"] == "unknown"
    assert "lesion" not in seed


def test_followup_seed_keeps_old_history_contract_but_uses_new_language_space():
    seed = v2.seed_for_case(_case("intent_clarify_followup"), v2.random.Random(1))
    assert seed["history_topic"]
    assert seed["followup"].endswith("?")
    assert any(marker in seed["followup"] for marker in ("ca đêm", "một bên má", "theo dõi", "không hợp", "tách vùng", "đi công tác", "khẩu trang", "cuối tuần", "nhầm thứ tự"))


def test_json_is_checked_before_embedding():
    case = _case("lesion_cyst")
    invalid_semantic = FakeSemantic([0.0])
    invalid = _record("mụn nang sâu đau", content="not-json")
    result = v2.assess_candidate(
        invalid,
        case,
        invalid["meta"]["seed"],
        semantic_filter=invalid_semantic,
        state=CorpusGateState(ANCHOR),
        contaminated=set(),
        anchor=ANCHOR,
    )
    assert result.reason == "json_invalid"
    assert invalid_semantic.calls == 0

    semantic = FakeSemantic([0.899999])
    valid = _record("mụn nang sâu đau")
    result = v2.assess_candidate(
        valid,
        case,
        valid["meta"]["seed"],
        semantic_filter=semantic,
        state=CorpusGateState(ANCHOR),
        contaminated=set(),
        anchor=ANCHOR,
    )
    assert result.accepted


def test_exact_train_or_val_overlap_is_still_rejected():
    valid = _record("mụn nang sâu đau")
    result = v2.assess_candidate(
        valid,
        _case("lesion_cyst"),
        valid["meta"]["seed"],
        semantic_filter=FakeSemantic([0.0]),
        state=CorpusGateState(ANCHOR),
        contaminated={v2.user_turn_hash("mụn nang sâu đau")},
        anchor=ANCHOR,
    )
    assert result.reason == "exact_train_or_val"


def test_internal_cosine_rejects_at_090():
    semantic = FakeSemantic([0.90])
    record = _record("mụn nang sâu đau")
    result = v2.assess_candidate(
        record,
        _case("lesion_cyst"),
        record["meta"]["seed"],
        semantic_filter=semantic,
        state=CorpusGateState(ANCHOR),
        contaminated=set(),
        anchor=ANCHOR,
    )
    assert result.reason == "eval_cosine"


def test_build_tops_up_after_cosine_reject_and_only_finalizes_when_full(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    case = v2.replace(_case("lesion_cyst"), quota=2)
    counter = 0

    async def fake_attempt(provider, selected, seed, anchor):
        nonlocal counter
        counter += 1
        user = f"mụn nang sâu đau mẫu {counter}"
        record = _record(user, record_id=f"r{counter}")
        record["meta"]["seed"] = {"required_user_cues": [user]}
        return record, record["meta"]["seed"], None

    monkeypatch.setattr(v2, "_attempt", fake_attempt)
    semantic = FakeSemantic([0.90, 0.0, 0.1])
    out = tmp_path / "intake_eval.v2.jsonl"
    records, got, rejects, complete = asyncio.run(v2.build(
        ANCHOR,
        (case,),
        provider=object(),
        semantic_filter=semantic,
        contaminated=set(),
        out=out,
        seed=1,
        attempts_factor=3,
        concurrency=2,
        generator_id="deepseek:deepseek-v4-pro",
    ))
    assert complete and out.is_file()
    assert len(records) == 2 and got[case.name] == 2
    assert rejects[f"{case.name}:eval_cosine"] == 1
    partial, audit = v2._paths_for(out)
    assert partial.is_file() and audit.is_file()


def test_checkpoint_is_revalidated_and_can_finalize_without_new_api_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    case = v2.replace(_case("lesion_cyst"), quota=1)
    out = tmp_path / "intake_eval.v2.jsonl"
    partial, _ = v2._paths_for(out)
    record = _record("mụn nang sâu đau checkpoint")
    record["meta"]["seed"] = {"required_user_cues": ["mụn nang sâu đau checkpoint"]}
    v2.write_jsonl(partial, [record])

    async def must_not_call(*args, **kwargs):
        raise AssertionError("checkpoint đủ quota thì không được gọi API")

    monkeypatch.setattr(v2, "_attempt", must_not_call)
    semantic = FakeSemantic([0.0])
    records, got, _, complete = asyncio.run(v2.build(
        ANCHOR,
        (case,),
        provider=object(),
        semantic_filter=semantic,
        contaminated=set(),
        out=out,
        seed=1,
        attempts_factor=10,
        concurrency=2,
        generator_id="deepseek:deepseek-v4-pro",
    ))
    assert complete and out.is_file()
    assert len(records) == 1 and got[case.name] == 1
    assert semantic.accepts == 1


def test_defaults_match_approved_runtime_contract():
    assert v2.DEFAULT_MODEL == "deepseek-v4-pro"
    assert v2.MAX_OUTPUT_TOKENS == 8_000
    assert len(v2.SMOKE_CASE_NAMES) == 10
    assert v2._paths_for(Path("intake_eval.v2.jsonl")) == (
        Path("intake_eval.v2.partial.jsonl"),
        Path("intake_eval.v2.audit.jsonl"),
    )
