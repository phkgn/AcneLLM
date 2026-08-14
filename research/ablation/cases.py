"""Case schema for the oracle-ablation eval.

Standalone on purpose: no import from `evaluation/`, no reuse of any existing
dataset. One case carries the *target output of every module*, so any module can
be replaced by its oracle without touching the other two.

    golden_intake   -> what a perfect intaker would emit
    golden_context  -> what a perfect retriever would return
    reference_answer-> what a perfect generator writes from the two above

Run `python -m ablation.cases` for the self-check.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Flat slot vocabulary. The intaker is scored per-slot against these keys only;
# anything the real intaker emits outside this set is ignored, anything inside
# it and missing counts as a miss.
SLOT_KEYS = (
    "intent",              # advise | knowledge | clarify | reject | refuse
    "age", "sex", "skin_type", "duration_weeks",
    "is_pregnant", "is_breastfeeding",
    "allergies", "medications", "current_products",
    "lesion_types", "inflammation_level", "lesion_distribution",
    "treatment_goals", "red_flags",
)
SET_SLOTS = frozenset({
    "allergies", "medications", "current_products",
    "lesion_types", "lesion_distribution", "treatment_goals", "red_flags",
})


@dataclass
class Case:
    case_id: str
    message: str                                    # the user turn, verbatim
    golden_intake: dict                             # oracle slots
    golden_context: list[str]                       # oracle evidence passages
    reference_answer: str                           # oracle answer
    must_cover: list[str] = field(default_factory=list)      # rubric: required facts
    must_not_say: list[str] = field(default_factory=list)    # rubric: forbidden claims
    tags: list[str] = field(default_factory=list)            # e.g. pregnancy, red_flag, ood

    def validate(self) -> list[str]:
        errs = []
        if not self.case_id or not self.message.strip():
            errs.append(f"{self.case_id or '<no id>'}: empty case_id/message")
        unknown = set(self.golden_intake) - set(SLOT_KEYS)
        if unknown:
            errs.append(f"{self.case_id}: unknown slots {sorted(unknown)}")
        for k in SET_SLOTS & set(self.golden_intake):
            if not isinstance(self.golden_intake[k], list):
                errs.append(f"{self.case_id}: slot '{k}' must be a list")
        if not self.golden_context:
            errs.append(f"{self.case_id}: golden_context empty (oracle RAG has nothing to inject)")
        if not self.must_cover:
            errs.append(f"{self.case_id}: must_cover empty (judge has no rubric)")
        return errs


def load(path: str | Path) -> list[Case]:
    """Load + validate a jsonl case file. Raises on any schema error."""
    cases = [Case(**json.loads(line)) for line in
             Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    errs = [e for c in cases for e in c.validate()]
    ids = [c.case_id for c in cases]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        errs.append(f"duplicate case_id: {sorted(dupes)}")
    if errs:
        raise ValueError("invalid case file:\n" + "\n".join(errs[:20]))
    return cases


def dump(cases: list[Case], path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        "\n".join(json.dumps(asdict(c), ensure_ascii=False) for c in cases) + "\n",
        encoding="utf-8",
    )


def slot_scores(pred: dict, gold: dict) -> dict:
    """Per-slot correctness in [0,1]. Set slots use Jaccard, scalars exact match.

    Only slots present in `gold` are scored: a golden case does not assert that
    every field is absent, it asserts the ones it knows about.
    """
    out = {}
    for k, g in gold.items():
        p = pred.get(k)
        if k in SET_SLOTS:
            gs = {str(x).strip().lower() for x in (g or [])}
            ps = {str(x).strip().lower() for x in (p or [])}
            out[k] = 1.0 if not gs and not ps else len(gs & ps) / max(1, len(gs | ps))
        else:
            out[k] = float(_norm(p) == _norm(g))
    return out


def _norm(v):
    if isinstance(v, str):
        return v.strip().lower() or None
    return v


def demo() -> None:
    c = Case(
        case_id="t1", message="em bầu 3 tháng bị mụn viêm ở cằm dùng tretinoin được không",
        golden_intake={"intent": "advise", "is_pregnant": True,
                       "lesion_types": ["papule"], "lesion_distribution": ["chin"],
                       "medications": ["tretinoin"]},
        golden_context=["Retinoid đường bôi chống chỉ định trong thai kỳ."],
        reference_answer="Không nên dùng tretinoin khi mang thai...",
        must_cover=["tretinoin chống chỉ định thai kỳ"],
        must_not_say=["tretinoin an toàn cho bà bầu"],
    )
    assert c.validate() == [], c.validate()

    s = slot_scores({"is_pregnant": True, "medications": ["Tretinoin"], "age": 20},
                    c.golden_intake)
    assert s["is_pregnant"] == 1.0
    assert s["medications"] == 1.0                    # case-insensitive set match
    assert s["intent"] == 0.0                         # missing -> miss
    assert s["lesion_types"] == 0.0
    assert "age" not in s                             # not asserted by gold -> not scored

    bad = Case("t2", "x", {"nonsense": 1}, [], "", [])
    assert len(bad.validate()) == 3, bad.validate()
    print("cases.py OK")


if __name__ == "__main__":
    demo()
