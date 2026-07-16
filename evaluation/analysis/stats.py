"""Statistical tests cho paired evaluation (§9 blueprint). Stdlib-only, unit-tested.

- paired_bootstrap: 95% CI của mean difference (Koehn 2004)
- wilcoxon_signed_rank: normal approximation với tie/zero handling (Pratt)
- mcnemar_exact: binomial exact test trên discordant pairs
- holm_bonferroni, cliffs_delta, win_tie_loss
"""
from __future__ import annotations

import math
import random
from statistics import mean


def paired_bootstrap(a: list[float], b: list[float], n_resamples: int = 10_000,
                     seed: int = 42) -> dict:
    """CI 95% cho mean(a-b) + p-value xấp xỉ (2 phía) từ tỉ lệ dấu."""
    assert len(a) == len(b) and a, "paired: cùng độ dài, không rỗng"
    diffs = [x - y for x, y in zip(a, b)]
    rng = random.Random(seed)
    n = len(diffs)
    boot_means = []
    for _ in range(n_resamples):
        sample = [diffs[rng.randrange(n)] for _ in range(n)]
        boot_means.append(mean(sample))
    boot_means.sort()
    lo = boot_means[int(0.025 * n_resamples)]
    hi = boot_means[int(0.975 * n_resamples)]
    # p-value: 2 * min(P(mean<=0), P(mean>=0))
    p_le = sum(1 for m in boot_means if m <= 0) / n_resamples
    p_ge = sum(1 for m in boot_means if m >= 0) / n_resamples
    return {
        "mean_diff": round(mean(diffs), 6),
        "ci95": [round(lo, 6), round(hi, 6)],
        "p_value": round(min(1.0, 2 * min(p_le, p_ge)), 6),
        "significant": not (lo <= 0 <= hi),
        "n": n,
    }


def wilcoxon_signed_rank(a: list[float], b: list[float]) -> dict:
    """Wilcoxon signed-rank, normal approximation (đủ cho n≥20), zero-diff loại bỏ,
    tie correction trong variance."""
    diffs = [x - y for x, y in zip(a, b) if x != y]
    n = len(diffs)
    if n < 10:
        return {"n": n, "warning": "n<10 — dùng sign test/bootstrap thay", "p_value": None}
    ranked = sorted((abs(d), d > 0) for d in diffs)
    # average ranks với ties
    ranks: list[float] = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and ranked[j + 1][0] == ranked[i][0]:
            j += 1
        avg_rank = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[k] = avg_rank
        i = j + 1
    w_plus = sum(r for r, (_, pos) in zip(ranks, ranked) if pos)
    mu = n * (n + 1) / 4
    # tie correction
    tie_counts: dict[float, int] = {}
    for val, _ in ranked:
        tie_counts[val] = tie_counts.get(val, 0) + 1
    tie_term = sum(t ** 3 - t for t in tie_counts.values())
    sigma2 = n * (n + 1) * (2 * n + 1) / 24 - tie_term / 48
    if sigma2 <= 0:
        return {"n": n, "warning": "variance=0", "p_value": None}
    z = (w_plus - mu) / math.sqrt(sigma2)
    p = 2 * (1 - _norm_cdf(abs(z)))
    return {"n": n, "w_plus": w_plus, "z": round(z, 4), "p_value": round(p, 6)}


def mcnemar_exact(a: list[bool], b: list[bool]) -> dict:
    """Exact binomial McNemar trên discordant pairs (Dietterich 1998)."""
    n01 = sum(1 for x, y in zip(a, b) if not x and y)   # a sai, b đúng
    n10 = sum(1 for x, y in zip(a, b) if x and not y)   # a đúng, b sai
    n_disc = n01 + n10
    if n_disc == 0:
        return {"n01": 0, "n10": 0, "p_value": 1.0}
    k = min(n01, n10)
    p = sum(math.comb(n_disc, i) for i in range(k + 1)) / (2 ** n_disc) * 2
    return {"n01": n01, "n10": n10, "p_value": round(min(1.0, p), 6)}


def holm_bonferroni(pvalues: dict[str, float], alpha: float = 0.05) -> dict[str, dict]:
    """Holm (1979): sort tăng dần, so p_i với alpha/(m-i)."""
    items = sorted(((k, v) for k, v in pvalues.items() if v is not None),
                   key=lambda kv: kv[1])
    m = len(items)
    out: dict[str, dict] = {}
    rejected_so_far = True
    for i, (key, p) in enumerate(items):
        threshold = alpha / (m - i)
        reject = rejected_so_far and p <= threshold
        rejected_so_far = reject
        out[key] = {"p": p, "threshold": round(threshold, 6), "significant": reject}
    return out


def cliffs_delta(a: list[float], b: list[float]) -> float:
    """Cliff's δ ∈ [-1,1]; |δ|<0.147 negligible, <0.33 small, <0.474 medium (Romano 2006)."""
    gt = sum(1 for x in a for y in b if x > y)
    lt = sum(1 for x in a for y in b if x < y)
    return round((gt - lt) / (len(a) * len(b)), 4) if a and b else 0.0


def win_tie_loss(a: list[float], b: list[float], eps: float = 1e-9) -> dict:
    win = sum(1 for x, y in zip(a, b) if x - y > eps)
    loss = sum(1 for x, y in zip(a, b) if y - x > eps)
    return {"win": win, "tie": len(a) - win - loss, "loss": loss}


def _norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))
