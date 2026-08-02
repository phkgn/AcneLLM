"""Attribution report over the arm matrix.

Four questions, four sections:

1. HEADROOM  — how much better does each module *could* get?
   delta_m = score(arm where m is oracle) - score(RRR). The three numbers the
   brief asks for. Reported with a paired bootstrap CI, because all arms are run
   on the same cases and the per-case difference is far tighter than the
   difference of the two means.

2. ATTRIBUTION — how much of the total gap does each module *own*?
   Shapley value over the 2^3 lattice. Single-oracle deltas do not add up to
   OOO - RRR whenever modules interact (a perfect intaker is worth more once the
   context is also perfect). Shapley values do add up exactly, which is what
   makes "module X accounts for Y% of the gap" a defensible sentence.

3. INTERACTION — is the pipeline coupled or separable? The 2-way contrasts. A
   near-zero interaction is itself a finding: the modules can be improved
   independently.

4. OBSERVED — what actually goes wrong at runtime, on the real distribution?
   Oracle substitution measures *potential*; this measures *incidence*:
   P(fail | intaker missed a slot) vs P(fail | intaker was exact), plus the
   latency each module spends buying its contribution.

    python -m ablation.report --run ablation/runs/main.jsonl.judged.jsonl
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import random
from collections import defaultdict
from pathlib import Path

MODULES = ["intaker", "rag", "generator"]
B = 2000                                     # bootstrap resamples
random.seed(0)


def _load(path):
    rows = [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]
    by_case = defaultdict(dict)
    for r in rows:
        by_case[r["case_id"]][r["arm"]] = r
    return rows, dict(by_case)


def _mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else float("nan")


def _boot(by_case, stat, b=B):
    """Paired bootstrap: resample cases, not observations. Returns (est, lo, hi)."""
    ids = list(by_case)
    est = stat(ids)
    draws = []
    for _ in range(b):
        s = [random.choice(ids) for _ in ids]
        v = stat(s)
        if not math.isnan(v):
            draws.append(v)
    draws.sort()
    if not draws:
        return est, float("nan"), float("nan")
    return est, draws[int(0.025 * len(draws))], draws[int(0.975 * len(draws)) - 1]


def _arm_stat(by_case, arm, key="score"):
    def f(ids):
        return _mean(by_case[i][arm][key] for i in ids
                     if arm in by_case[i] and by_case[i][arm].get(key) is not None)
    return f


def _delta_stat(by_case, a, b, key="score"):
    def f(ids):
        d = [by_case[i][a][key] - by_case[i][b][key] for i in ids
             if a in by_case[i] and b in by_case[i]]
        return _mean(d)
    return f


def _v(by_case, ids, subset, key="score"):
    """Coalition value: mean score of the arm where exactly `subset` are oracle."""
    arm = "".join("O" if m in subset else "R" for m in MODULES)
    vals = [by_case[i][arm][key] for i in ids if arm in by_case[i]]
    return _mean(vals)


def _shapley(by_case, ids, key="score"):
    n = len(MODULES)
    fact = [math.factorial(k) for k in range(n + 1)]
    out = {}
    for m in MODULES:
        rest = [x for x in MODULES if x != m]
        phi = 0.0
        for k in range(n):
            for S in itertools.combinations(rest, k):
                w = fact[k] * fact[n - k - 1] / fact[n]
                phi += w * (_v(by_case, ids, set(S) | {m}, key) - _v(by_case, ids, set(S), key))
        out[m] = phi
    return out


def _fmt(x, nd=3):
    return "n/a" if (x is None or (isinstance(x, float) and math.isnan(x))) else f"{x:+.{nd}f}" if nd and x < 0 else f"{x:.{nd}f}"


def _regression(path, baseline_path, key="score") -> list[str]:
    """So lần chạy này với một lần chạy trước, ghép theo (case_id, arm).

    Đây là phần biến module từ một nghiên cứu một-lần thành một cái eval: câu hỏi
    không còn là "module nào là nút thắt" mà là "lần này có tệ đi so với lần
    trước không, và tệ ở case nào".
    """
    _, cur = _load(path)
    _, base = _load(baseline_path)
    L, A = [], None
    L.append(f"\n## 8. So với `{Path(baseline_path).name}`\n")

    shared_cases = sorted(set(cur) & set(base))
    if not shared_cases:
        L.append("> Không có case chung — hai lần chạy dùng case set khác nhau, "
                 "không so được. Kiểm `cases_sha256` trong hai file `.meta.json`.")
        return L

    for meta_path in (Path(path).with_suffix(".meta.json"),
                      Path(baseline_path).with_suffix(".meta.json")):
        if meta_path.exists():
            m = json.loads(meta_path.read_text(encoding="utf-8"))
            L.append(f"- `{meta_path.name}`: commit `{m.get('git_commit')}`"
                     f"{' (dirty)' if m.get('git_dirty') else ''}"
                     f" · cases `{m.get('cases_sha256')}` · judge `{m['models']['judge']}`")
    L.append("")

    arms = sorted({a for cid in shared_cases for a in cur[cid] if a in base[cid]})
    L.append("| arm | trước | sau | Δ | 95% CI (paired) | kết luận |")
    L.append("|---|---|---|---|---|---|")
    for arm in arms:
        ids = [c for c in shared_cases if arm in cur[c] and arm in base[c]]
        if not ids:
            continue
        pairs = {c: (base[c][arm][key], cur[c][arm][key]) for c in ids}

        def stat(sample, p=pairs):
            return _mean(p[c][1] - p[c][0] for c in sample)

        sub = {c: cur[c] for c in ids}
        est, lo, hi = _boot(sub, stat)
        verdict = ("TỆ ĐI" if hi < 0 else "tốt lên" if lo > 0 else "trong nhiễu")
        L.append(f"| `{arm}` | {_fmt(_mean(v[0] for v in pairs.values()))} | "
                 f"{_fmt(_mean(v[1] for v in pairs.values()))} | **{_fmt(est)}** | "
                 f"[{_fmt(lo)}, {_fmt(hi)}] | {verdict} |")

    drops = sorted(
        ((base[c][a][key] - cur[c][a][key], c, a) for c in shared_cases
         for a in cur[c] if a in base[c] and base[c][a][key] - cur[c][a][key] > 0.05),
        reverse=True,
    )[:15]
    L.append(f"\n### Case tụt điểm ({len(drops)} nặng nhất, ngưỡng 0.05)\n")
    if not drops:
        L.append("Không case nào tụt quá 0.05.")
    else:
        L.append("| case | arm | trước | sau | Δ | mới vi phạm an toàn |")
        L.append("|---|---|---|---|---|---|")
        for d, c, a in drops:
            newly = cur[c][a].get("violated") and not base[c][a].get("violated")
            L.append(f"| `{c}` | `{a}` | {_fmt(base[c][a][key])} | {_fmt(cur[c][a][key])} | "
                     f"-{d:.3f} | {'CÓ' if newly else ''} |")
    return L


def build(path, key="score", baseline: str | None = None) -> str:
    rows, by_case = _load(path)
    arms = sorted({r["arm"] for r in rows})
    ids = list(by_case)
    complete = [i for i in ids if len(by_case[i]) == len(arms)]
    L = []
    A = L.append

    A(f"# Ablation report — `{Path(path).name}`\n")
    A(f"metric = `{key}` · cases = {len(ids)} (complete across all arms: {len(complete)}) "
      f"· arms = {len(arms)} · bootstrap B = {B}\n")
    if len(complete) < len(ids):
        A(f"> {len(ids) - len(complete)} case(s) missing at least one arm — paired "
          f"statistics use only the cases that have both arms of the pair.\n")

    # ── 1. arms ──────────────────────────────────────────────────────────────
    A("\n## 0. Arms\n")
    A("| arm | intaker | rag | generator | score | quality | coverage | faithful | safety fail | ms |")
    A("|---|---|---|---|---|---|---|---|---|---|")
    for arm in arms:
        rs = [r for r in rows if r["arm"] == arm]
        est, lo, hi = _boot(by_case, _arm_stat(by_case, arm, key))
        ms = _mean(r["ms_intake"] + r["ms_rag"] + r["ms_gen"] for r in rs)
        A(f"| `{arm}` | {arm[0]} | {arm[1]} | {arm[2]} | "
          f"**{_fmt(est)}** [{_fmt(lo)}, {_fmt(hi)}] | {_fmt(_mean(r['quality'] for r in rs))} | "
          f"{_fmt(_mean(r['coverage'] for r in rs))} | {_fmt(_mean(r['faithful'] for r in rs))} | "
          f"{_mean(1.0 if r['violated'] else 0.0 for r in rs):.1%} | {ms:,.0f} |")

    # ── 2. headroom ──────────────────────────────────────────────────────────
    A("\n## 1. Headroom — one module made perfect\n")
    A("| swap | arm | Δ vs RRR | 95% CI (paired) | significant |")
    A("|---|---|---|---|---|")
    for m, arm in zip(MODULES, ["ORR", "ROR", "RRO"]):
        if arm not in arms:
            continue
        est, lo, hi = _boot(by_case, _delta_stat(by_case, arm, "RRR", key))
        A(f"| perfect **{m}** | `{arm}` | **{_fmt(est)}** | [{_fmt(lo)}, {_fmt(hi)}] | "
          f"{'yes' if lo > 0 or hi < 0 else 'no'} |")
    if "OOO" in arms:
        est, lo, hi = _boot(by_case, _delta_stat(by_case, "OOO", "RRR", key))
        A(f"| **all three** (ceiling) | `OOO` | **{_fmt(est)}** | [{_fmt(lo)}, {_fmt(hi)}] | "
          f"{'yes' if lo > 0 or hi < 0 else 'no'} |")
        A("\nIf the three single deltas sum to less than the ceiling delta, the modules "
          "are complementary (fixing one unlocks the others); if more, they are "
          "redundant (they were compensating for each other).")

    # ── 3. shapley ───────────────────────────────────────────────────────────
    if all(a in arms for a in ("".join(x) for x in itertools.product("RO", repeat=3))):
        A("\n## 2. Attribution — Shapley over the full 2³ lattice\n")
        base, ceil = _v(by_case, ids, set(), key), _v(by_case, ids, set(MODULES), key)
        phi = _shapley(by_case, ids, key)
        tot = ceil - base
        A(f"total gap RRR → OOO = **{_fmt(tot)}** (from {_fmt(base)} to {_fmt(ceil)})\n")
        A("| module | Shapley φ | 95% CI | share of gap |")
        A("|---|---|---|---|")
        for m in MODULES:
            e, lo, hi = _boot(by_case, lambda s, m=m: _shapley(by_case, s, key)[m])
            A(f"| **{m}** | {_fmt(e)} | [{_fmt(lo)}, {_fmt(hi)}] | "
              f"{(e / tot if tot else float('nan')):.0%} |")
        A(f"\nΣφ = {_fmt(sum(phi.values()))} = total gap (exact by construction).")

        # ── 4. interactions ──────────────────────────────────────────────────
        A("\n## 3. Interaction — are the modules separable?\n")
        A("| pair | interaction | reading |")
        A("|---|---|---|")
        for a, b in itertools.combinations(MODULES, 2):
            def inter(s, a=a, b=b):
                return (_v(by_case, s, {a, b}, key) - _v(by_case, s, {a}, key)
                        - _v(by_case, s, {b}, key) + _v(by_case, s, set(), key))
            e, lo, hi = _boot(by_case, inter)
            sign = ("synergy — worth fixing together" if lo > 0 else
                    "redundancy — they overlap" if hi < 0 else
                    "separable — fix independently")
            A(f"| {a} × {b} | {_fmt(e)} [{_fmt(lo)}, {_fmt(hi)}] | {sign} |")

    # ── 5. intrinsic intaker accuracy ────────────────────────────────────────
    base_rows = [r for r in rows if r["arm"] == "RRR"]
    if base_rows:
        A("\n## 4. Intrinsic accuracy — the real intaker vs golden slots\n")
        A(f"mean slot score (RRR) = **{_fmt(_mean(r['slot_score'] for r in base_rows))}**\n")
        per = defaultdict(list)
        for r in base_rows:
            for k, v in r["slot_detail"].items():
                per[k].append(v)
        A("| slot | accuracy | n asserted |")
        A("|---|---|---|")
        for k, v in sorted(per.items(), key=lambda kv: _mean(kv[1])):
            A(f"| `{k}` | {_fmt(_mean(v))} | {len(v)} |")

        # ── 6. observed error propagation ────────────────────────────────────
        A("\n## 5. Observed propagation — incidence, not potential\n")
        # ponytail: median split, not exact-match. With ~15 slots a perfect
        # slot_score is vanishingly rare, so an exact/not-exact split collapses
        # into one group and says nothing. The exact group is still shown when
        # it happens to be non-empty.
        ss = sorted(r["slot_score"] for r in base_rows)
        med = ss[len(ss) // 2] if ss else 0.0
        groups = [
            (f"intake good (slot ≥ {med:.2f})", [r for r in base_rows if r["slot_score"] >= med]),
            (f"intake poor (slot < {med:.2f})", [r for r in base_rows if r["slot_score"] < med]),
            ("— of which intake exact (1.00)", [r for r in base_rows if r["slot_score"] >= 0.999]),
        ]
        A("| baseline subgroup | n | mean score | safety fail rate |")
        A("|---|---|---|---|")
        for name, g in groups:
            if g:
                A(f"| {name} | {len(g)} | {_fmt(_mean(r[key] for r in g))} | "
                  f"{_mean(1.0 if r['violated'] else 0.0 for r in g):.1%} |")
        good, poor = groups[0][1], groups[1][1]
        if good and poor:
            gap = _mean(r[key] for r in good) - _mean(r[key] for r in poor)
            A(f"\nObserved intake gap on the live distribution: **{_fmt(gap)}** "
              f"(vs headroom {_fmt(_delta_stat(by_case, 'ORR', 'RRR', key)(ids))} from §1). "
              "Headroom larger than the observed gap means the intaker fails on cases "
              "the current set under-samples; smaller means the oracle slots are also "
              "buying something the real intaker could never recover from text alone.")
        A("\nHeadroom (§1) says how much a module *could* give; this says how often it "
          "actually costs something on the live distribution. A module with large "
          "headroom but low incidence is a low-priority fix.")

        # ── 7. cost of each module ───────────────────────────────────────────
        A("\n## 6. What each module costs at runtime (baseline arm)\n")
        A("| stage | mean ms | share |")
        A("|---|---|---|")
        tot_ms = _mean(r["ms_intake"] + r["ms_rag"] + r["ms_gen"] for r in base_rows) or 1
        for lbl, k in (("intaker", "ms_intake"), ("rag", "ms_rag"), ("generator", "ms_gen")):
            m = _mean(r[k] for r in base_rows)
            A(f"| {lbl} | {m:,.0f} | {m / tot_ms:.0%} |")

    # ── 8. by tag ────────────────────────────────────────────────────────────
    tags = sorted({t for r in rows for t in r.get("tags", [])})
    if tags and "RRR" in arms:
        A("\n## 7. Where the headroom lives — by tag\n")
        A("| tag | n | RRR | Δ intaker | Δ rag | Δ generator |")
        A("|---|---|---|---|---|---|")
        for t in tags:
            sub = {i: v for i, v in by_case.items()
                   if any(t in r.get("tags", []) for r in v.values())}
            if not sub:
                continue
            cells = []
            for arm in ("ORR", "ROR", "RRO"):
                cells.append(_fmt(_delta_stat(sub, arm, "RRR", key)(list(sub)))
                             if arm in arms else "n/a")
            A(f"| `{t}` | {len(sub)} | {_fmt(_arm_stat(sub, 'RRR', key)(list(sub)))} | "
              + " | ".join(cells) + " |")

    # ── 9. dài hơn có được điểm cao hơn không ────────────────────────────────
    if any("chars" in r for r in rows):
        xs = [(r["chars"], r[key]) for r in rows if r.get("chars")]
        if len(xs) > 8:
            mx, my = _mean(x for x, _ in xs), _mean(y for _, y in xs)
            num = sum((x - mx) * (y - my) for x, y in xs)
            den = (sum((x - mx) ** 2 for x, _ in xs) * sum((y - my) ** 2 for _, y in xs)) ** 0.5
            r_len = num / den if den else 0.0
            A(f"\n## 9. Kiểm tra gaming độ dài\n")
            A(f"tương quan (số ký tự, `{key}`) = **{r_len:+.3f}** "
              f"· dài trung bình {_mean(x for x, _ in xs):,.0f} ký tự\n")
            A("`coverage` thưởng cho việc nêu được nhiều ý rubric, nên câu trả lời dài "
              "hơn có lợi thế cơ học. Tương quan cao (|r| > 0.5) nghĩa là điểm đang đo "
              "độ dài chứ không đo chất lượng — khi đó phải chuẩn hóa theo độ dài hoặc "
              "thêm phạt dài vào rubric.")

    if baseline:
        L.extend(_regression(path, baseline, key))

    return "\n".join(L) + "\n"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--run", default="ablation/runs/main.jsonl.judged.jsonl")
    p.add_argument("--metric", default="score", choices=["score", "quality", "coverage", "faithful"])
    p.add_argument("--baseline", default="", help="file .judged.jsonl của lần chạy trước")
    p.add_argument("--out", default="ablation/runs/report.md")
    a = p.parse_args()
    md = build(a.run, a.metric, baseline=a.baseline or None)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(md, encoding="utf-8")
    print(md)


def demo() -> None:
    """Self-check on a synthetic lattice with known Shapley values."""
    import tempfile
    # v(S) built so that: intaker=+0.2, rag=+0.1, generator=+0.4, no interaction.
    w = {"intaker": 0.2, "rag": 0.1, "generator": 0.4}
    lines = []
    for ci in range(12):
        for arm in ("".join(x) for x in itertools.product("RO", repeat=3)):
            s = 0.3 + sum(w[m] for m, c in zip(MODULES, arm) if c == "O")
            lines.append(json.dumps({
                "case_id": f"c{ci}", "arm": arm, "tags": ["t"], "answer": "",
                "context": [], "slots": {}, "n_context": 0,
                "slot_score": 1.0 if ci % 2 else 0.5, "slot_detail": {"age": 1.0},
                "ms_intake": 10, "ms_rag": 20, "ms_gen": 30, "chars": 400,
                "score": s, "quality": s, "coverage": s, "faithful": 1.0,
                "violated": False,
            }))
    d = Path(tempfile.mkdtemp())
    f = d / "d.jsonl"
    f.write_text("\n".join(lines), encoding="utf-8")
    _, bc = _load(f)
    phi = _shapley(bc, list(bc))
    for m, exp in w.items():
        assert abs(phi[m] - exp) < 1e-9, (m, phi[m], exp)
    assert abs(sum(phi.values()) - (_v(bc, list(bc), set(MODULES)) - _v(bc, list(bc), set()))) < 1e-9
    assert "Shapley" in build(f)

    # regression: bản "sau" tụt 0.10 ở mọi ô, phải bị gọi tên là TỆ ĐI
    worse = d / "worse.jsonl"
    worse.write_text("\n".join(
        json.dumps({**json.loads(x), "score": json.loads(x)["score"] - 0.10})
        for x in lines), encoding="utf-8")
    md = build(worse, baseline=f)
    assert "TỆ ĐI" in md and "tốt lên" not in md, md[md.index("## 8."):]
    assert "Case tụt điểm" in md
    # đảo chiều: bản "sau" tốt hơn
    assert "tốt lên" in build(f, baseline=worse)
    # case set khác nhau -> từ chối so, không âm thầm so bừa
    other = d / "other.jsonl"
    other.write_text("\n".join(
        json.dumps({**json.loads(x), "case_id": "zz" + json.loads(x)["case_id"]})
        for x in lines), encoding="utf-8")
    assert "Không có case chung" in build(f, baseline=other)
    print("report.py OK")


if __name__ == "__main__":
    main()
