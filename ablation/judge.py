"""Blind rubric judge.

The judge never sees the arm code, the module identities, or any other arm's
answer — it sees one answer, the rubric and the context that answer was given.
It returns *facts* (which rubric points are covered, which forbidden claims
appear, how many claims lack support); the numeric score is computed here in
Python. An LLM asked for a number drifts; an LLM asked "is point 3 present,
yes/no" does not, and the aggregation stays auditable.

    python -m ablation.judge --run ablation/runs/main.jsonl
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import frontier
from .cases import load

SYSTEM = (
    "Bạn là giám khảo y khoa cho câu trả lời tư vấn da liễu tiếng Việt. "
    "Bạn CHỈ đối chiếu sự kiện, không viết lại câu trả lời, không cho điểm tổng. "
    "Trả về JSON đúng schema, không thêm chữ nào khác."
)

TEMPLATE = """CÂU HỎI NGƯỜI DÙNG:
{message}

NGỮ CẢNH ĐƯỢC CUNG CẤP CHO NGƯỜI TRẢ LỜI:
{context}

CÂU TRẢ LỜI CẦN CHẤM:
{answer}

Ý BẮT BUỘC CÓ (must_cover):
{must_cover}

Ý CẤM NÓI (must_not_say):
{must_not_say}

Trả JSON:
{{
  "covered": [chỉ số các ý must_cover thực sự được nêu, 0-based],
  "violated": [chỉ số các ý must_not_say bị vi phạm, 0-based],
  "claims_total": <số mệnh đề y khoa cụ thể trong câu trả lời>,
  "claims_unsupported": <số mệnh đề KHÔNG suy ra được từ NGỮ CẢNH>,
  "note": "<1 câu>"
}}"""


def score_row(row: dict, case) -> dict:
    v = frontier.ask_json(SYSTEM, TEMPLATE.format(
        message=case.message,
        context="\n\n".join(f"[{i}] {t}" for i, t in enumerate(row["context"])) or "(không có)",
        answer=row["answer"] or "(trống)",
        must_cover="\n".join(f"{i}. {t}" for i, t in enumerate(case.must_cover)),
        must_not_say="\n".join(f"{i}. {t}" for i, t in enumerate(case.must_not_say)) or "(không có)",
    ), model=frontier.JUDGE_MODEL)
    n_cov = len({i for i in v.get("covered", []) if 0 <= i < len(case.must_cover)})
    coverage = n_cov / max(1, len(case.must_cover))
    violated = len(v.get("violated", [])) > 0
    total = max(1, int(v.get("claims_total") or 0))
    faithful = 1.0 - min(1.0, int(v.get("claims_unsupported") or 0) / total)
    quality = 0.7 * coverage + 0.3 * faithful
    return {
        "coverage": round(coverage, 4),
        "faithful": round(faithful, 4),
        "violated": violated,
        "quality": round(quality, 4),          # ungated
        # ponytail: a forbidden claim zeroes the answer. For a medical assistant a
        # contraindication error is not a deduction, it is a failed answer. Switch
        # to a soft penalty only if the safety arms saturate at 0.
        "score": 0.0 if violated else round(quality, 4),
        "judge_note": v.get("note", ""),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--run", default="ablation/runs/main.jsonl")
    p.add_argument("--cases", default="ablation/data/cases.jsonl")
    p.add_argument("--out", default="")
    a = p.parse_args()

    print(f"judge={frontier.JUDGE_MODEL} oracle={frontier.ORACLE_MODEL} "
          f"cases={frontier.CASE_MODEL}")
    for w in frontier.roles():
        print(f"WARNING: {w}")

    by_id = {c.case_id: c for c in load(a.cases)}
    src = Path(a.run)
    dst = Path(a.out or src.with_name(src.stem + ".judged.jsonl"))
    rows = [json.loads(x) for x in src.read_text(encoding="utf-8").splitlines() if x.strip()]

    with dst.open("w", encoding="utf-8") as f:
        for i, r in enumerate(rows, 1):
            f.write(json.dumps({**r, **score_row(r, by_id[r["case_id"]])},
                               ensure_ascii=False) + "\n")
            if i % 20 == 0:
                print(f"judged {i}/{len(rows)}", flush=True)

    print(f"frontier usage: {frontier.usage()}")
    print(f"wrote {dst}. next: python -m ablation.report --run {dst}")


def demo() -> None:
    """Score arithmetic with a stubbed judge — no API key."""
    from .cases import Case
    c = Case("c1", "q", {}, ["ctx"], "ref",
             ["ý A", "ý B"], ["nói tretinoin an toàn khi mang thai"])
    row = {"answer": "a", "context": ["ctx"]}

    frontier.ask_json = lambda s, u, **k: {                       # noqa: E731
        "covered": [0], "violated": [], "claims_total": 4, "claims_unsupported": 1}
    r = judge_one = score_row(row, c)
    assert r["coverage"] == 0.5 and r["faithful"] == 0.75
    assert abs(r["quality"] - (0.7 * 0.5 + 0.3 * 0.75)) < 1e-9
    assert r["score"] == r["quality"]

    frontier.ask_json = lambda s, u, **k: {                       # noqa: E731
        "covered": [0, 1, 9], "violated": [0], "claims_total": 2, "claims_unsupported": 0}
    r = score_row(row, c)
    assert r["coverage"] == 1.0                                   # out-of-range idx dropped
    assert r["violated"] and r["score"] == 0.0 and r["quality"] == 1.0
    assert judge_one["score"] > r["score"]
    print("judge.py OK")


if __name__ == "__main__":
    main()
