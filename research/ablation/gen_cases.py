"""Generate the case set from scratch with the frontier model.

Nothing is reused from the existing eval datasets — the whole point of the
oracle arms is that `golden_intake` / `golden_context` / `reference_answer` are
mutually consistent, and legacy files were never built that way.

Provenance matters: an oracle-RAG arm that injects invented evidence measures
nothing. Two modes:

  --source-dir DIR   passages must be quoted verbatim from files in DIR
                     (recommended: point it at the real guideline corpus)
  (default)          the model writes the passages and every case is tagged
                     `needs_source_review` — do not publish a number from these
                     until a human has checked the evidence.

    python -m ablation.gen_cases --n 60 --source-dir guideline_docs --out ablation/data/cases.jsonl
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from . import frontier
from .cases import Case, SLOT_KEYS, dump, load

# Seed grid. The product of these is the coverage claim; cases are sampled from
# it rather than free-associated, so the set is auditable and reproducible.
PROFILES = ["nữ 17 tuổi da dầu", "nam 22 tuổi da hỗn hợp", "nữ 28 tuổi mang thai 3 tháng",
            "nữ 31 tuổi đang cho con bú", "nam 35 tuổi da nhạy cảm",
            "nữ 24 tuổi đang uống isotretinoin", "nam 19 tuổi mụn lưng"]
SITUATIONS = ["mụn viêm sưng đỏ ở cằm 3 tuần", "mụn đầu đen ở mũi lâu năm",
              "mụn nang đau, để lại sẹo rỗ", "mụn bùng phát sau khi đổi sữa rửa mặt",
              "thâm sau mụn không mờ", "mụn kèm sốt và sưng hạch",
              "hỏi chung về cơ chế hình thành mụn", "hỏi về một chủ đề không phải da liễu"]
STYLES = ["viết teencode, sai chính tả", "viết đầy đủ, lịch sự",
          "viết cụt ngủn 5-7 chữ", "kể lể dài dòng lẫn chi tiết thừa"]

SYSTEM = f"""Bạn xây dựng bộ test cho một trợ lý tư vấn da mụn tiếng Việt.
Mỗi case phải tự nhất quán: golden_intake, golden_context và reference_answer
phải khớp nhau — reference_answer chỉ được suy ra từ golden_context và golden_intake.

Chỉ dùng các khóa slot sau trong golden_intake (bỏ khóa không biết, không bịa):
{', '.join(SLOT_KEYS)}
intent ∈ advise | knowledge | clarify | reject | refuse.
Các slot dạng danh sách: allergies, medications, current_products, lesion_types,
lesion_distribution, treatment_goals, red_flags.

Trả JSON: {{"cases": [{{
  "case_id": "...", "message": "<câu người dùng gõ, đúng phong cách yêu cầu>",
  "golden_intake": {{...}},
  "golden_context": ["<đoạn bằng chứng 1>", "..."],
  "reference_answer": "<câu trả lời chuẩn>",
  "must_cover": ["<ý bắt buộc>", ...],
  "must_not_say": ["<khẳng định sai/nguy hiểm>", ...],
  "tags": ["..."]
}}]}}"""


def _sources(d: Path, k: int = 6) -> str:
    files = [p for p in d.rglob("*") if p.suffix.lower() in {".md", ".txt"}][:200]
    picked = random.sample(files, min(k, len(files))) if files else []
    return "\n\n".join(f"### {p.name}\n{p.read_text(encoding='utf-8', errors='ignore')[:2500]}"
                       for p in picked)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=60)
    p.add_argument("--batch", type=int, default=5)
    p.add_argument("--source-dir", default="")
    p.add_argument("--out", default="ablation/data/cases.jsonl")
    p.add_argument("--seed", type=int, default=0)
    a = p.parse_args()
    random.seed(a.seed)

    src_dir = Path(a.source_dir) if a.source_dir else None
    if src_dir and not src_dir.exists():
        raise SystemExit(f"--source-dir not found: {src_dir}")

    out: list[Case] = []
    while len(out) < a.n:
        combos = [(random.choice(PROFILES), random.choice(SITUATIONS), random.choice(STYLES))
                  for _ in range(a.batch)]
        spec = "\n".join(f"- case {len(out)+i+1}: hồ sơ={c[0]} | tình huống={c[1]} | văn phong={c[2]}"
                         for i, c in enumerate(combos))
        if src_dir:
            prompt = (f"TÀI LIỆU NGUỒN (golden_context phải TRÍCH NGUYÊN VĂN từ đây):\n"
                      f"{_sources(src_dir)}\n\nSinh {a.batch} case:\n{spec}")
        else:
            prompt = (f"Sinh {a.batch} case. Không có tài liệu nguồn: viết golden_context "
                      f"theo kiến thức da liễu chuẩn và thêm tag "
                      f"\"needs_source_review\".\n{spec}")

        data = frontier.ask_json(SYSTEM, prompt, model=frontier.CASE_MODEL)
        for i, raw in enumerate(data.get("cases", [])):
            raw["case_id"] = f"c{len(out)+1:03d}"
            raw["golden_intake"] = {k: v for k, v in (raw.get("golden_intake") or {}).items()
                                    if k in SLOT_KEYS}
            raw["tags"] = list(raw.get("tags") or []) + ([] if src_dir else ["needs_source_review"])
            c = Case(**{k: raw.get(k) for k in Case.__dataclass_fields__ if k in raw})
            errs = c.validate()
            if errs:
                print(f"  drop {c.case_id}: {errs[0]}")
                continue
            out.append(c)
            if len(out) >= a.n:
                break
        print(f"{len(out)}/{a.n}", flush=True)

    dump(out, a.out)
    load(a.out)                       # fail loudly if the written file is invalid
    print(f"frontier usage: {frontier.usage()}")
    print(f"wrote {a.out} ({len(out)} cases)")
    if not src_dir:
        print("WARNING: all cases tagged needs_source_review — evidence is model-written.")


if __name__ == "__main__":
    main()
