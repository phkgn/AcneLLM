"""Log + checkpoint + bảng ASCII cho ablation run.

Một cơ chế cho ba nhu cầu: mỗi dòng xong được ghi ngay vào `rows.jsonl`.
Đó vừa là log đầy đủ, vừa là checkpoint để chạy tiếp, vừa là chống mất khi
crash giữa chừng — 780 lượt gọi API mà đổ hết vì lỗi ở dòng 700 thì quá đắt.
"""
from __future__ import annotations

import json
import re
import textwrap
from pathlib import Path
from typing import Any

BOX = {"tl": "┌", "tr": "┐", "bl": "└", "br": "┘", "h": "─", "v": "│",
       "lt": "├", "rt": "┤", "tt": "┬", "bt": "┴", "x": "┼"}
_WS = re.compile(r"\s+")


def _flat(text: Any, limit: int = 0) -> str:
    out = _WS.sub(" ", str(text or "")).strip()
    return out[: limit - 1] + "…" if limit and len(out) > limit else out


class RunLog:
    """Append-only. `rows.jsonl` là nguồn sự thật; results.json dựng lại từ nó."""

    def __init__(self, run_dir: Path, fingerprint: str, *, resume: bool = True):
        run_dir.mkdir(parents=True, exist_ok=True)
        self.rows_path = run_dir / "rows.jsonl"
        self.log_path = run_dir / "run.log"
        self.stamp_path = run_dir / ".fingerprint"
        self.fingerprint = fingerprint
        self._rows: dict[tuple[str, str], dict[str, Any]] = {}

        # Bộ câu hỏi đổi thì checkpoint cũ vô nghĩa — thà bỏ còn hơn ghép nhầm.
        stale = (
            self.stamp_path.exists()
            and self.stamp_path.read_text(encoding="utf-8").strip() != fingerprint
        )
        if resume and self.rows_path.exists() and not stale:
            self._rows = self._load()
        elif stale:
            self.say("⚠ checkpoint cũ thuộc bộ câu hỏi khác — bỏ qua, chạy lại từ đầu")
            self.rows_path.unlink(missing_ok=True)
        self.stamp_path.write_text(fingerprint, encoding="utf-8")

    def _load(self) -> dict[tuple[str, str], dict[str, Any]]:
        loaded: dict[tuple[str, str], dict[str, Any]] = {}
        for line in self.rows_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue          # dòng cuối bị cắt do crash — bỏ, chạy lại dòng đó
            loaded[(entry["arm"], entry["record"]["sample_id"])] = entry["record"]
        return loaded

    # ── checkpoint ────────────────────────────────────────────────────────
    def cached(self, arm: str, sample_id: str) -> dict[str, Any] | None:
        return self._rows.get((arm, sample_id))

    def append(self, arm: str, record: dict[str, Any]) -> None:
        self._rows[(arm, record["sample_id"])] = record
        with self.rows_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"arm": arm, "record": record},
                                    ensure_ascii=False) + "\n")

    def rows_for(self, arm: str, order: list[str]) -> list[dict[str, Any]]:
        return [self._rows[(arm, sid)] for sid in order if (arm, sid) in self._rows]

    def done_count(self, arm: str) -> int:
        return sum(1 for key in self._rows if key[0] == arm)

    # ── log ───────────────────────────────────────────────────────────────
    def say(self, text: str = "") -> None:
        print(text, flush=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(text + "\n")


# ── khối trace từng dòng ──────────────────────────────────────────────────

def row_block(
    *,
    arm: str,
    arm_desc: str,
    index: int,
    total: int,
    sample: dict[str, Any],
    record: dict[str, Any],
    duration_s: float,
    width: int = 96,
) -> str:
    """Mọi thứ cần để debug một dòng, không phải mở results.json."""
    trace = record.get("trace") or {}
    scorecard = record.get("scorecard") or {}
    inner = width - 2
    lines = [f"{BOX['tl']}{BOX['h']} {arm}  {sample['sample_id']}  "
             f"({index}/{total})  {arm_desc}".ljust(width - 1, " ") + BOX['tr']]

    def field(label: str, value: str, indent: int = 11) -> None:
        text = _flat(value)
        if not text:
            return
        for i, chunk in enumerate(textwrap.wrap(text, inner - indent) or [""]):
            head = f" {label:<9} " if i == 0 else " " * (indent + 1)
            lines.append(f"{BOX['v']}{head}{chunk}".ljust(width - 1) + BOX['v'])

    points = sample.get("expected_answer_points") or []
    field("task", f"{sample.get('intent_label') or '?'} · "
                  f"{len(points)} ý mong đợi"
                  + (f" · {points[0]}" if points else ""))
    field("query", sample.get("user_query"))

    # Arm oracle: slot ĐƯỢC BƠM. Arm thật: slot intaker RÚT ĐƯỢC.
    # Không trộn hai thứ — trước đây fallback về key của user_context trong
    # dataset, tức in ra thứ dataset có chứ không phải thứ intaker lấy được.
    intake_src = trace.get("intake_source") or ("oracle" if arm[0] == "O" else "real")
    if intake_src == "oracle":
        label, slots = "bơm", trace.get("oracle_injected_fields")
    else:
        label, slots = "rút", trace.get("extracted_slots")
    shown = ", ".join(map(str, slots)) if slots else ("—" if slots == [] else "?")
    field("intaker", f"{intake_src} · intent={trace.get('primary_intent') or '?'} · "
                     f"{label}=[{shown}]")

    chunks = record.get("used_chunks") or []
    field("context", f"{trace.get('retrieval_source') or '?'} · {len(chunks)} chunk"
                     + (f" · {', '.join(chunks[:3])}" if chunks else ""))
    field("generator", f"{trace.get('generator_model') or '?'} · "
                       f"{trace.get('temperature_policy') or '?'}")
    field("answer", f"{_flat(record.get('answer'), 200)}"
                    f"  [{len(record.get('answer') or '')} ký tự]")

    if scorecard:
        field("metric", " · ".join([
            f"quality={scorecard.get('answer_quality')}",
            f"tone={scorecard.get('role_tone')}",
            f"safety={'pass' if scorecard.get('safety_pass') else 'FAIL'}",
            f"refusal={scorecard.get('refusal_fidelity')}",
        ]))
        # Mặt context ra None ở arm tắt RAG — không in dòng rỗng.
        if scorecard.get("context_relevance") is not None:
            field("context+", " · ".join([
                f"relevance={_num(scorecard.get('context_relevance'))}/5",
                f"precision={_num(scorecard.get('context_precision'))}",
                f"sufficiency={_num(scorecard.get('context_sufficiency'))}/5",
                f"ranking={_num(scorecard.get('ranking_quality'))}",
                f"grounded={_num(scorecard.get('groundedness'))}/5",
            ]))
        reasons = (scorecard.get("details") or {}).get("safety_fail_reasons") or []
        if reasons:
            field("!safety", ", ".join(reasons))
    if record.get("error"):
        field("!error", record["error"])

    status = "ok" if record.get("ok") else (record.get("error") or "fail")
    lines.append(f"{BOX['bl']}{BOX['h']} {status} · {duration_s:.1f}s".ljust(
        width - 1, BOX['h']) + BOX['br'])
    return "\n".join(lines)


# ── bảng ASCII ────────────────────────────────────────────────────────────

def table(headers: list[str], rows: list[list[str]], align: str = "") -> str:
    align = (align + "l" * len(headers))[: len(headers)]
    widths = [max(len(headers[i]), *(len(str(r[i])) for r in rows)) if rows
              else len(headers[i]) for i in range(len(headers))]

    def line(left: str, mid: str, right: str) -> str:
        return left + mid.join(BOX["h"] * (w + 2) for w in widths) + right

    def row(cells: list[str]) -> str:
        out = []
        for index, cell in enumerate(cells):
            text = str(cell)
            out.append(" " + (text.rjust(widths[index]) if align[index] == "r"
                              else text.ljust(widths[index])) + " ")
        return BOX["v"] + BOX["v"].join(out) + BOX["v"]

    return "\n".join([
        line(BOX["tl"], BOX["tt"], BOX["tr"]),
        row(headers),
        line(BOX["lt"], BOX["x"], BOX["rt"]),
        *(row(r) for r in rows),
        line(BOX["bl"], BOX["bt"], BOX["br"]),
    ])


def arm_summary_table(arms: dict[str, Any]) -> str:
    """Cột chất lượng in `trung bình (trung vị)`.

    Bảng cũ chỉ có trung vị. Trên thang nguyên 1-5, trung vị của ~200 dòng gần
    như luôn rơi đúng số nguyên, nên sáu arm hiện ra giống hệt nhau và người đọc
    kết luận "mọi cấu hình như nhau" trong khi trung bình chênh nhau rõ rệt.
    """
    headers = ["arm", "n", "ok", "fail", "quality", "tone", "sai↓", "thiếu↓",
               "ctx.rel", "ctx.suff", "rank", "ground", "safety✗", "$judge"]
    rows = []
    for arm, payload in arms.items():
        meta = payload.get("summary") or {}
        med = meta.get("face_medians") or {}
        avg = meta.get("face_means") or {}

        def both(face: str) -> str:
            """Trung bình là con số dẫn dắt, trung vị để trong ngoặc."""
            if not isinstance(avg.get(face), (int, float)):
                return _num(med.get(face))
            return f"{avg[face]:.2f} ({_num(med.get(face))[:4]})"

        rows.append([
            arm,
            meta.get("rows", 0),
            meta.get("successful", 0),
            meta.get("failed", 0),
            both("answer_quality"),
            both("role_tone"),
            both("incorrect_content"),
            both("missing_content"),
            both("context_relevance"),
            both("context_sufficiency"),
            both("ranking_quality"),
            both("groundedness"),
            meta.get("safety_failures", 0),
            f"{meta.get('judge_cost_usd', 0):.3f}",
        ])
    return (table(headers, rows, align="lrrrrrrrrrrrrr")
            + "\n  ô chất lượng = trung bình (trung vị)  ·  ↓ = thấp là tốt")


def delta_table(summary: dict[str, Any], baseline: str) -> str:
    headers = [f"arm vs {baseline}", "face", "n", "Δ trung bình", "CI 95%", "+/−/="]
    rows = []
    for arm, payload in (summary.get("arms") or {}).items():
        for face, stat in (payload.get("quality") or {}).items():
            low, high = (stat.get("bootstrap_95_ci_mean") or [None, None])[:2]
            crosses = low is None or high is None or (low <= 0 <= high)
            rows.append([
                arm, face, stat.get("paired_n", 0), _num(stat.get("mean_delta")),
                f"[{_num(low)}, {_num(high)}]" + ("" if crosses else "  *"),
                f"{stat.get('increased', 0)}/{stat.get('decreased', 0)}"
                f"/{stat.get('unchanged', 0)}",
            ])
    return table(headers, rows, align="llrrll") + "\n  * = CI không cắt 0"


def _num(value: Any) -> str:
    return "—" if not isinstance(value, (int, float)) else f"{value:.3f}"


def demo() -> None:
    out = table(["a", "bb"], [["1", "2"]], align="lr")
    assert out.count("\n") == 4 and "│" in out
    assert _num(None) == "—" and _num(0.5) == "0.500"
    assert _flat("a   b\nc", 4) == "a b…"
    block = row_block(
        arm="RRR", arm_desc="real+real+local", index=1, total=2,
        sample={"sample_id": "q-1", "user_query": "mụn ở cằm?", "intent_label": "advise"},
        record={"ok": True, "answer": "vì nội tiết", "used_chunks": ["c1"],
                "scorecard": {"answer_quality": 4, "role_tone": 4,
                              "context_relevance": 4.2, "context_precision": 0.8,
                              "context_sufficiency": 4.0, "ranking_quality": 0.95,
                              "groundedness": 5.0, "safety_pass": True,
                              "refusal_fidelity": True},
                "trace": {"intake_source": "real", "primary_intent": "advise"}},
        duration_s=1.0)
    assert "q-1" in block and "quality=4" in block and block.startswith("┌")
    assert "relevance=4.200/5" in block and "ranking=0.950" in block
    print("trace demo OK")


if __name__ == "__main__":
    demo()
