#!/usr/bin/env python3
"""Chấm lại câu trả lời ĐÃ LƯU — không chạy lại model.

Vì sao tồn tại: `answer_quality` gộp "nói sai" với "không nói", mà hai lỗi đó cần
hai cách sửa khác nhau (sai là vấn đề kiến thức, thiếu là vấn đề bao phủ — Med-PaLM
tách thành hai trục vì lý do này). Rubric đã tách thành `incorrect_content` và
`missing_content`, nhưng artifact 1182 dòng chấm trước khi tách nên chưa có.

Chạy lại toàn bộ ablation để lấy hai trục đó là ~3 giờ và vài chục nghìn token
sinh — vô lý, vì câu trả lời KHÔNG đổi. Chúng nằm nguyên trong `rows.jsonl`.
Script này chỉ gọi lại judge: ~40 phút và vài đô.

Điểm context KHÔNG chấm lại — chúng độc lập với câu trả lời và đã có sẵn; chấm
lại chỉ thêm nhiễu và tiền. Chúng được bê nguyên sang scorecard mới.

Prompt và luật hợp lệ dùng THẲNG `run_ablation._judge_prompt` /
`_score_candidate`. Chép lại rubric sang đây là cách chắc chắn nhất để hai bên
lệch nhau sau vài tháng rồi không ai so được số nữa.

Ghi append-only nên dừng giữa chừng chạy lại là tiếp, không mất gì.

Usage:
    python -m evaluation.runners.rescore
    python -m evaluation.runners.rescore --arms RRR,RRO --limit 20
    python -m evaluation.runners.rescore --no-cache --workers 8
"""
from __future__ import annotations

import argparse
import collections
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import statistics as st
import sys
import threading
import time
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[3]
for _p in (ROOT, ROOT / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from evaluation.common import utcnow  # noqa: E402
from evaluation.judges.clients import JudgeClient  # noqa: E402
from evaluation.judges.context import FACES as CONTEXT_FACES  # noqa: E402
from evaluation.judges.rubrics import LOWER_IS_BETTER  # noqa: E402
from evaluation.metrics.scorecard import build_scorecard  # noqa: E402
from evaluation.runners.run_ablation import _score_candidate  # noqa: E402

DEFAULT_INPUT = ROOT / "research/evaluation/reports/full_eval/ablation/rows.jsonl"
DEFAULT_OUTPUT = ROOT / "research/evaluation/reports/rescore"
DEFAULT_JUDGE = "deepseek-v4-pro"
ANSWER_FACES = ("answer_quality", "role_tone", "incorrect_content", "missing_content")


def load_rows(path: Path) -> list[dict[str, Any]]:
    """Đọc từng dòng qua file handle, KHÔNG dùng splitlines().

    `splitlines()` cắt cả ở \\u2028/\\u2029 — ký tự hợp lệ bên trong chuỗi JSON.
    Một lần đã làm 24.393 dòng thành 24.398 dòng hỏng vì đúng lỗi này.
    """
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{number}: JSON hỏng — {exc}") from exc
    return rows


def rebuilt_context(card: Mapping[str, Any]) -> dict[str, Any]:
    """Bê điểm context cũ sang, không chấm lại. Chúng không phụ thuộc câu trả lời."""
    return {
        **{face: card.get(face) for face in CONTEXT_FACES},
        "details": (card.get("details") or {}).get("context"),
    }


def rescore_one(judge: JudgeClient, arm: str, record: Mapping[str, Any]) -> dict[str, Any]:
    """Một dòng -> scorecard mới. `record` đã chứa đủ trường mà judge cần."""
    card = record.get("scorecard") or {}
    judged = _score_candidate(judge, record, str(record.get("answer") or ""))
    return {
        "arm": arm,
        "record": {
            **record,
            "judge_reason": judged.get("reason"),
            "scorecard": build_scorecard(
                record,
                record,
                judged,
                actual_intent=(card.get("details") or {}).get("actual_intent"),
                context_result=rebuilt_context(card),
            ),
        },
    }


def _mean(values: list[float]) -> float | None:
    return round(st.mean(values), 4) if values else None


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_arm: dict[str, list[Mapping[str, Any]]] = collections.defaultdict(list)
    for row in rows:
        by_arm[row["arm"]].append(row["record"].get("scorecard") or {})

    out: dict[str, Any] = {}
    for arm, cards in sorted(by_arm.items()):
        faces = {
            face: _mean([
                c[face] for c in cards
                if isinstance(c.get(face), (int, float)) and not isinstance(c.get(face), bool)
            ])
            for face in ANSWER_FACES
        }
        reasons: collections.Counter[str] = collections.Counter()
        for card in cards:
            for reason in (card.get("details") or {}).get("safety_fail_reasons") or []:
                reasons[reason] += 1
        # RQ3: lỗi chủ yếu là bịa, thiếu, hay khuyến nghị nguy hiểm.
        # Một dòng có thể dính nhiều loại -> đếm theo dòng, KHÔNG cộng ra 100%.
        n = len(cards)
        out[arm] = {
            "n": n,
            "faces": faces,
            "safety_fail": sum(1 for c in cards if c.get("safety_pass") is False),
            "safety_fail_reasons": dict(reasons.most_common()),
            "loi_theo_loai": {
                "noi_sai": sum(1 for c in cards if (c.get("incorrect_content") or 0) > 0),
                "bo_sot": sum(1 for c in cards if (c.get("missing_content") or 0) > 0),
                "khong_an_toan": sum(1 for c in cards if c.get("safety_pass") is False),
                "sach_ca_ba": sum(
                    1 for c in cards
                    if not (c.get("incorrect_content") or 0)
                    and not (c.get("missing_content") or 0)
                    and c.get("safety_pass") is not False
                ),
            },
        }
    return out


def _print_summary(summary: Mapping[str, Any]) -> None:
    print(f"\n{'arm':6}{'n':>5}{'quality':>9}{'tone':>7}{'sai↓':>7}{'thiếu↓':>9}{'unsafe':>8}")
    for arm, data in summary.items():
        f = data["faces"]
        def fmt(face: str) -> str:
            v = f.get(face)
            return f"{v:.2f}" if isinstance(v, (int, float)) else "—"
        print(f"{arm:6}{data['n']:>5}{fmt('answer_quality'):>9}{fmt('role_tone'):>7}"
              f"{fmt('incorrect_content'):>7}{fmt('missing_content'):>9}"
              f"{data['safety_fail']:>8}")
    print("\n  ↓ = thấp là tốt:", ", ".join(sorted(LOWER_IS_BETTER)))

    print(f"\n{'arm':6}{'nói sai':>10}{'bỏ sót':>9}{'unsafe':>9}{'sạch cả ba':>13}")
    for arm, data in summary.items():
        b, n = data["loi_theo_loai"], data["n"] or 1
        print(f"{arm:6}{b['noi_sai']:>6} {b['noi_sai']/n:>3.0%}"
              f"{b['bo_sot']:>5} {b['bo_sot']/n:>3.0%}"
              f"{b['khong_an_toan']:>5} {b['khong_an_toan']/n:>3.0%}"
              f"{b['sach_ca_ba']:>8} {b['sach_ca_ba']/n:>3.0%}")
    print("\n  Một dòng dính nhiều loại -> các cột KHÔNG cộng ra 100%.")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=str(DEFAULT_INPUT))
    ap.add_argument("--out", "--output", dest="out", default=str(DEFAULT_OUTPUT))
    ap.add_argument("--arms", default="", help="lọc, vd RRR,RRO. Mặc định: tất cả")
    ap.add_argument("--limit", type=int, default=0, help="0 = tất cả")
    ap.add_argument("--judge-model", default=DEFAULT_JUDGE)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--no-cache", action="store_true",
                    help="chấm mới 100%%: bỏ qua cache judge (vẫn ghi)")
    ap.add_argument("--restart", action="store_true", help="bỏ checkpoint, chấm lại từ đầu")
    args = ap.parse_args(argv)

    src = Path(args.input)
    if not src.exists():
        raise SystemExit(f"Không thấy {src} — chạy run_ablation trước.")
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_rows = out_dir / "rows.jsonl"
    if args.restart and out_rows.exists():
        out_rows.unlink()

    rows = load_rows(src)
    wanted = {a.strip() for a in args.arms.split(",") if a.strip()}
    if wanted:
        rows = [r for r in rows if r.get("arm") in wanted]

    # Checkpoint: (arm, sample_id) đã chấm thì bỏ qua. Dừng giữa chừng không mất gì.
    done: set[tuple[str, str]] = set()
    if out_rows.exists():
        for row in load_rows(out_rows):
            done.add((row.get("arm", ""), str((row.get("record") or {}).get("sample_id"))))

    todo = [
        r for r in rows
        if (r.get("arm", ""), str((r.get("record") or {}).get("sample_id"))) not in done
        and (r.get("record") or {}).get("answer")
    ]
    if args.limit:
        todo = todo[: args.limit]

    print(f"{len(rows)} dòng · {len(done)} đã chấm · {len(todo)} cần chấm · "
          f"judge {args.judge_model} · {args.workers} luồng")
    if not todo and not done:
        raise SystemExit("Không có dòng nào có câu trả lời để chấm.")

    judge = JudgeClient(model=args.judge_model,
                        use_cache=not args.no_cache)
    write_lock = threading.Lock()
    failed: list[dict[str, str]] = []
    t0 = time.time()
    finished = 0

    # Ghi ngay mỗi dòng xong, KHÔNG gom cuối. 40 phút mà crash phút 39 thì mất sạch.
    with out_rows.open("a", encoding="utf-8") as sink, \
            ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {
            pool.submit(rescore_one, judge, r["arm"], r["record"]): r
            for r in todo
        }
        for future in as_completed(futures):
            source = futures[future]
            sample_id = str((source.get("record") or {}).get("sample_id"))
            try:
                result = future.result()
            except Exception as exc:                      # noqa: BLE001
                # Một dòng hỏng không được giết cả lượt — judge trả JSON dị dạng
                # ở dòng 900 mà mất 39 phút công là quá đắt.
                failed.append({"arm": source.get("arm", ""), "sample_id": sample_id,
                               "error": f"{type(exc).__name__}: {exc}"})
            else:
                with write_lock:
                    sink.write(json.dumps(result, ensure_ascii=False) + "\n")
                    sink.flush()
            finished += 1
            print(f"\r  {finished}/{len(todo)} · "
                  f"{(time.time() - t0) / max(finished, 1):.1f}s/dòng · "
                  f"lỗi {len(failed)}", end="", flush=True)
    print()

    all_rows = load_rows(out_rows)
    summary = summarise(all_rows)
    (out_dir / "summary.json").write_text(
        json.dumps({
            "generated_at": utcnow(),
            "source": str(src),
            "judge_model": args.judge_model,
            "judge_cache_read": not args.no_cache,
            "judge_cost_usd": round(getattr(judge, "total_cost_usd", 0.0), 4),
            "n": len(all_rows),
            "failed": failed,
            "arms": summary,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    _print_summary(summary)
    if failed:
        print(f"\n  ⚠ {len(failed)} dòng lỗi, KHÔNG tính vào điểm:")
        for item in failed[:5]:
            print(f"     {item['arm']}/{item['sample_id']}: {item['error'][:70]}")
        print("     chạy lại lệnh này để chấm nốt (checkpoint bỏ qua dòng đã xong)")
    print(f"\n  chi phí judge: ${getattr(judge, 'total_cost_usd', 0.0):.3f}")
    print(f"  {out_dir}")


def demo() -> None:
    """Kiểm phần logic thuần, không gọi mạng."""
    card = {
        "answer_quality": 3, "role_tone": 4,
        "context_relevance": 4.0, "context_precision": 0.8,
        "context_sufficiency": 3.0, "ranking_quality": 0.9, "groundedness": 4.0,
        "details": {"context": {"n_chunks": 5}, "actual_intent": "advise"},
    }
    ctx = rebuilt_context(card)
    assert ctx["context_relevance"] == 4.0 and ctx["details"] == {"n_chunks": 5}

    rows = [
        {"arm": "RRR", "record": {"scorecard": {
            "answer_quality": 3, "role_tone": 4,
            "incorrect_content": 2, "missing_content": 0, "safety_pass": True,
            "details": {"safety_fail_reasons": []}}}},
        {"arm": "RRR", "record": {"scorecard": {
            "answer_quality": 1, "role_tone": 3,
            "incorrect_content": 0, "missing_content": 3, "safety_pass": False,
            "details": {"safety_fail_reasons": ["forbidden_claim"]}}}},
        {"arm": "RRR", "record": {"scorecard": {
            "answer_quality": 5, "role_tone": 5,
            "incorrect_content": 0, "missing_content": 0, "safety_pass": True,
            "details": {"safety_fail_reasons": []}}}},
    ]
    s = summarise(rows)["RRR"]
    assert s["n"] == 3 and s["safety_fail"] == 1
    assert s["faces"]["answer_quality"] == 3.0
    assert s["loi_theo_loai"] == {"noi_sai": 1, "bo_sot": 1,
                                  "khong_an_toan": 1, "sach_ca_ba": 1}
    assert s["safety_fail_reasons"] == {"forbidden_claim": 1}

    # Judge CŨ chưa chấm hai mặt mới -> None, phải bị bỏ qua khi tính trung bình
    # chứ KHÔNG được coi là 0 (0 nghĩa là "không có lỗi" — ngược hẳn).
    old = [{"arm": "X", "record": {"scorecard": {
        "answer_quality": 2, "role_tone": 2,
        "incorrect_content": None, "missing_content": None, "safety_pass": True,
        "details": {}}}}]
    sx = summarise(old)["X"]
    assert sx["faces"]["incorrect_content"] is None
    assert sx["loi_theo_loai"]["noi_sai"] == 0

    # Đường đi thật của một dòng, judge giả nên không cần mạng.
    class FakeJudge:
        seen = ""

        def judge(self, prompt: str) -> dict:
            FakeJudge.seen = prompt
            return {"reason": "ok", "answer_quality": 4, "role_tone": 5,
                    "incorrect_content": 0, "missing_content": 1,
                    "forbidden_violated": False}

    record = {
        "sample_id": "q-1", "user_query": "mụn ở cằm do đâu?",
        "user_context": {"is_pregnant": True},
        "expected_answer_points": ["nội tiết"],
        "forbidden_claims": ["kê liều cụ thể"],
        "intent_label": "advise",
        "answer": "Mụn cằm thường liên quan nội tiết.",
        "scorecard": card,
    }
    out = rescore_one(FakeJudge(), "RRR", record)["record"]
    new = out["scorecard"]
    assert new["answer_quality"] == 4.0 and new["missing_content"] == 1.0
    # Điểm context BÊ NGUYÊN sang, không chấm lại -> không tốn tiền, không nhiễu.
    assert new["context_relevance"] == 4.0
    assert new["details"]["context"] == {"n_chunks": 5}
    assert new["details"]["actual_intent"] == "advise"
    # Câu trả lời và mọi trường gốc phải còn nguyên để chạy lại lần nữa vẫn được.
    assert out["answer"] == record["answer"] and out["sample_id"] == "q-1"
    # Rubric phải tới được judge, kèm dữ liệu riêng của câu hỏi (HealthBench).
    for must in ("incorrect_content", "missing_content", "nội tiết", "kê liều cụ thể"):
        assert must in FakeJudge.seen, f"prompt thiếu {must!r}"

    # Judge trả điểm ngoài thang phải NỔ chứ không được ghi âm thầm.
    class BadJudge:
        def judge(self, prompt: str) -> dict:
            return {"answer_quality": 4, "role_tone": 5,
                    "incorrect_content": 9, "missing_content": 0}

    try:
        rescore_one(BadJudge(), "RRR", record)
    except RuntimeError:
        pass
    else:
        raise AssertionError("điểm ngoài thang 0-3 phải raise")
    print("rescore demo OK")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        demo()
    else:
        main()
