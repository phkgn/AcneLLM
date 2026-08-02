"""Run the arm matrix.

An arm is a 3-character code over {R, O, N} — one character per module:

        position 0 = intaker      1 = retriever (RAG)     2 = generator
        R = the real product module (system under test)
        O = the oracle             (golden slots / golden context / frontier model)
        N = null                   (empty slots / no context / no-op) — off by default

Default matrix is the full 2^3 factorial over {R,O}: RRR (baseline) … OOO (ceiling).
The three arms named in the brief are ORR (perfect intaker), RRO (perfect
generator) and ROR (perfect context); the other four make the attribution in
report.py exact rather than additive-by-assumption.

    python -m ablation.run --cases ablation/data/cases.jsonl --out ablation/runs/main.jsonl
    python -m ablation.run ... --arms RRR,NRR,RNR   # add degrade arms
    python -m ablation.run ... --dry-run            # oracle-only, no Ollama/Chroma
"""
from __future__ import annotations

import argparse
import itertools
import json
import time
from pathlib import Path

from . import frontier
from .cases import Case, load, slot_scores

FACTORIAL = ["".join(a) for a in itertools.product("RO", repeat=3)]

GEN_SYSTEM = (
    "Bạn là trợ lý tư vấn chăm sóc da mụn cho người dùng Việt Nam. "
    "Chỉ dùng thông tin trong phần NGỮ CẢNH và HỒ SƠ để trả lời; không bịa. "
    "Nếu ngữ cảnh không đủ, nói rõ là chưa đủ căn cứ. "
    "Luôn tôn trọng chống chỉ định (thai kỳ, cho con bú, dị ứng, thuốc đang dùng). "
    "Trả lời tiếng Việt, ngắn gọn, có bước hành động cụ thể, "
    "kèm khuyến nghị đi khám khi có dấu hiệu nặng."
)


def _oracle_generate(case: Case, slots: dict, contexts: list[str]) -> str:
    ctx = "\n\n".join(f"[{i}] {t}" for i, t in enumerate(contexts)) or "(không có)"
    prof = json.dumps(slots, ensure_ascii=False)
    return frontier.ask(
        GEN_SYSTEM,
        f"CÂU HỎI: {case.message}\n\nHỒ SƠ: {prof}\n\nNGỮ CẢNH:\n{ctx}",
        model=frontier.ORACLE_MODEL,
    )


def run_case(case: Case, arms: list[str], dry: bool) -> list[dict]:
    """One case across all arms. Intake and retrieval are memoised per variant so
    an 8-arm sweep costs 2 intakes + 2 retrievals + 8 generations, not 8 of each."""
    from . import repo_adapter as R  # late import: --dry-run must not need the product

    states, ctxs, rows = {}, {}, []

    def state(v: str):
        if v not in states:
            t = time.perf_counter()
            states[v] = ({"R": lambda: R.intake_real(case.message),
                          "O": lambda: R.intake_from_slots(case.message, case.golden_intake),
                          "N": lambda: R.intake_from_slots(case.message, {})}[v](),
                         int((time.perf_counter() - t) * 1000))
        return states[v]

    def ctx(v: str, iv: str):
        if (v, iv) not in ctxs:
            t = time.perf_counter()
            out = {"R": lambda: R.retrieve_real(state(iv)[0]),
                   "O": lambda: list(case.golden_context),
                   "N": lambda: []}[v]()
            ctxs[(v, iv)] = (out, int((time.perf_counter() - t) * 1000))
        return ctxs[(v, iv)]

    for arm in arms:
        iv, rv, gv = arm
        if dry and "R" in (iv, rv, gv):
            continue
        st, t_in = state(iv)
        cx, t_rag = ctx(rv, iv)
        t = time.perf_counter()
        if gv == "R":
            answer = R.generate_real(st, cx)
        elif gv == "O":
            answer = _oracle_generate(case, st.slots, cx)
        else:
            answer = ""
        t_gen = int((time.perf_counter() - t) * 1000)

        sc = slot_scores(st.slots, case.golden_intake)
        rows.append({
            "case_id": case.case_id, "arm": arm, "tags": case.tags,
            "answer": answer, "slots": st.slots, "n_context": len(cx),
            "context": cx, "chars": len(answer),
            "slot_score": sum(sc.values()) / max(1, len(sc)),
            "slot_detail": sc,
            "ms_intake": t_in, "ms_rag": t_rag, "ms_gen": t_gen,
        })
    return rows


def _write_meta(out: Path, cases_path: str, arms: list[str], n_cases: int) -> None:
    """Provenance sidecar. Không có nó thì so hai lần chạy là vô nghĩa: điểm tụt
    có thể do model tệ đi, do đổi bản judge, do đổi case set, hay do đổi config —
    và không cách nào phân biệt về sau."""
    import hashlib
    import subprocess

    def _git(*a):
        try:
            return subprocess.run(["git", *a], capture_output=True, text=True,
                                  timeout=5).stdout.strip() or None
        except Exception:
            return None

    settings_snapshot = {}
    try:
        from acne_llm.config import settings
        settings_snapshot = {
            k: getattr(settings, k, None) for k in (
                "llm_model", "intake_model", "intake_mode", "embedding_model",
                "reranker_model", "chat_retrieve_top_k", "chat_rerank_top_k",
                "chat_rerank_floor", "chat_min_chunk_score", "reranker_min_sigmoid",
                "chat_max_chunks_per_source", "dense_max_distance",
            )
        }
    except Exception:
        pass

    meta = {
        "written_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "cases_file": str(cases_path),
        "cases_sha256": hashlib.sha256(Path(cases_path).read_bytes()).hexdigest()[:16],
        "n_cases": n_cases,
        "arms": arms,
        "models": {"case": frontier.CASE_MODEL, "oracle": frontier.ORACLE_MODEL,
                   "judge": frontier.JUDGE_MODEL},
        "git_commit": _git("rev-parse", "--short", "HEAD"),
        "git_dirty": bool(_git("status", "--porcelain")),
        "settings": settings_snapshot,
    }
    path = out.with_suffix(".meta.json")
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    if meta["git_dirty"]:
        print("WARNING: working tree bẩn — kết quả không gắn được với commit nào")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--cases", default="ablation/data/cases.jsonl")
    p.add_argument("--out", default="ablation/runs/main.jsonl")
    p.add_argument("--arms", default=",".join(FACTORIAL))
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--dry-run", action="store_true",
                   help="oracle-only arms; needs no Ollama/Chroma, only OPENAI_API_KEY")
    a = p.parse_args()

    arms = [x.strip().upper() for x in a.arms.split(",") if x.strip()]
    bad = [x for x in arms if len(x) != 3 or set(x) - set("RON")]
    if bad:
        raise SystemExit(f"bad arm codes: {bad}")

    cases = load(a.cases)
    if a.limit:
        cases = cases[: a.limit]

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    _write_meta(out, a.cases, arms, len(cases))
    done = set()
    if out.exists():                                    # resume
        for line in out.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                done.add((r["case_id"], r["arm"]))

    with out.open("a", encoding="utf-8") as f:
        for i, c in enumerate(cases, 1):
            todo = [x for x in arms if (c.case_id, x) not in done]
            if not todo:
                continue
            for row in run_case(c, todo, a.dry_run):
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            print(f"[{i}/{len(cases)}] {c.case_id} arms={','.join(todo)}", flush=True)

    print(f"frontier usage: {frontier.usage()}")
    print(f"wrote {out}. next: python -m ablation.judge --run {out}")


def demo() -> None:
    """Arm dispatch + memoisation, oracle path only — no product, no API key."""
    from .cases import Case
    frontier.ask = lambda s, u, **k: "ORACLE"                      # noqa: E731
    c = Case("c001", "bầu 3 tháng mụn viêm ở cằm",
             {"intent": "advise", "is_pregnant": True, "lesion_distribution": ["chin"]},
             ["Retinoid bôi chống chỉ định thai kỳ."], "ref",
             ["tránh tretinoin"], ["tretinoin an toàn"], ["pregnancy"])
    rows = {r["arm"]: r for r in run_case(c, ["ONO", "OOO", "NOO", "OON"], dry=True)}
    assert set(rows) == {"ONO", "OOO", "NOO", "OON"}
    assert rows["ONO"]["n_context"] == 0 and rows["OOO"]["n_context"] == 1
    assert rows["OOO"]["slot_score"] == 1.0                         # oracle intake
    assert rows["NOO"]["slot_score"] == 0.0                         # null intake
    assert rows["OON"]["answer"] == "" and rows["OOO"]["answer"] == "ORACLE"
    assert run_case(c, ["RRR"], dry=True) == []                     # dry skips real arms
    print("run.py OK")


if __name__ == "__main__":
    main()
