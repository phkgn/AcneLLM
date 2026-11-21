# -*- coding: utf-8 -*-
"""Phan tich phieu cham tay 145 cau RRR — bo sung cho judges/calibrate.py --import.

Vi sao can file nay chu khong chi dung calibrate.py:

1. RRR-only co phan bo lech nang (78/145 hang o muc answer_quality=3). Cohen's
   kappa phat rat nang khi marginal lech nhu vay — hai ben co the dong y 70% so
   hang ma kappa van gan 0. Do la kappa paradox (Feinstein & Cicchetti 1990),
   khong phai bang chung judge te. Nen file nay bao THEM:
     - percent agreement (khop tuyet doi)
     - percent agreement +-1 bac (thang thu tu, lech 1 bac la chap nhan duoc)
     - Gwet's AC1 (Gwet 2008) — chi so on dinh truoc marginal lech
   Trich dan AC1 va +-1 agreement ben canh kappa, dung trich moi kappa.

2. calibrate.py chi doc 4 truc diem. Phieu nay con co human_forbidden_violated,
   la doi chung truc tiep cho co safety lon nhat cua RRR.

3. Kiem dinh cong an toan: safety_pass cua he thong bat loi khi
   incorrect_content >= 3. File nay do precision/recall cua chinh nguong do so
   voi nguoi.

Chay:
    python phan_tich_rrr145.py sheet_da_cham.jsonl [key_rrr145.jsonl]
Khong can numpy.
"""
from __future__ import annotations
import json, sys, os
from collections import Counter

AXES = {"answer_quality": (1, 5), "role_tone": (1, 5),
        "incorrect_content": (0, 3), "missing_content": (0, 3)}
LOWER_IS_BETTER = {"incorrect_content", "missing_content"}
UNSAFE_INCORRECT_LEVEL = 3


def read_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def kappa(h, j, weighted=False):
    labels = sorted(set(h) | set(j))
    if len(labels) == 1:
        return 1.0
    pos = {l: i for i, l in enumerate(labels)}
    span = (len(labels) - 1) ** 2

    def d(a, b):
        return ((pos[a] - pos[b]) ** 2 / span) if weighted else (0.0 if a == b else 1.0)
    n = len(h)
    obs = sum(d(a, b) for a, b in zip(h, j)) / n
    exp = sum((h.count(a) / n) * (j.count(b) / n) * d(a, b) for a in labels for b in labels)
    if exp == 0:
        return 1.0 if obs == 0 else 0.0
    return round(1 - obs / exp, 4)


def gwet_ac1(h, j):
    """AC1: thay 'dong thuan ngau nhien' cua kappa bang uoc luong khong phu
    thuoc marginal cua tung nguoi cham. On dinh khi mot bac diem chiem da so."""
    labels = sorted(set(h) | set(j))
    q = len(labels)
    if q == 1:
        return 1.0
    n = len(h)
    pa = sum(1 for a, b in zip(h, j) if a == b) / n
    pe = 0.0
    for l in labels:
        pi = (h.count(l) + j.count(l)) / (2 * n)
        pe += pi * (1 - pi)
    pe /= (q - 1)
    if pe == 1:
        return 0.0
    return round((pa - pe) / (1 - pe), 4)


def spearman(x, y):
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            k = i + 1
            while k < len(order) and v[order[k]] == v[order[i]]:
                k += 1
            avg = (i + k - 1) / 2 + 1
            for t in order[i:k]:
                r[t] = avg
            i = k
        return r
    a, b = ranks(x), ranks(y)
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((v - ma) ** 2 for v in a) ** 0.5
    vb = sum((v - mb) ** 2 for v in b) ** 0.5
    if va == 0 or vb == 0:
        return 0.0
    return round(sum((p - ma) * (q_ - mb) for p, q_ in zip(a, b)) / (va * vb), 4)


def interpret_ac1(v):
    for t, s in ((0.81, "gan nhu hoan toan"), (0.61, "dang ke"),
                 (0.41, "vua phai"), (0.21, "yeu"), (0.01, "rat yeu")):
        if v >= t:
            return s
    return "khong hon ngau nhien"


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    sheet_p = argv[0]
    here = os.path.dirname(os.path.abspath(__file__))
    key_p = argv[1] if len(argv) > 1 else os.path.join(here, "key_rrr145.jsonl")

    key = {r["row_id"]: r for r in read_jsonl(key_p)}
    sheet = read_jsonl(sheet_p)

    pairs = {a: ([], []) for a in AXES}
    fb_h, fb_j = [], []
    skipped = 0
    for row in sheet:
        rid = row.get("row_id")
        if rid not in key:
            raise SystemExit("row_id %r khong co trong file khoa" % rid)
        jd = key[rid]["judge"]
        if any(row.get("human_" + a) is None for a in AXES):
            skipped += 1
            continue
        for a, (lo, hi) in AXES.items():
            v = row.get("human_" + a)
            if not isinstance(v, int) or isinstance(v, bool) or not lo <= v <= hi:
                raise SystemExit("row %s: human_%s = %r, phai la so nguyen %d..%d"
                                 % (rid, a, v, lo, hi))
            pairs[a][0].append(v)
            pairs[a][1].append(int(jd[a]))
        hv = row.get("human_forbidden_violated")
        if isinstance(hv, bool):
            fb_h.append(hv)
            fb_j.append(bool(key[rid].get("judge_forbidden_violated")))

    n = len(pairs["answer_quality"][0])
    if not n:
        raise SystemExit("Chua co hang nao cham du 4 truc.")

    out = {"schema_version": 1, "arm": "RRR", "source": os.path.basename(sheet_p),
           "n_graded": n, "n_skipped_incomplete": skipped, "axes": {}}

    print("=" * 74)
    print("PHAN TICH PHIEU CHAM TAY — ARM RRR   (n = %d, bo qua %d hang chua du)" % (n, skipped))
    print("=" * 74)
    print("%-19s %5s %6s %6s %7s %7s %7s %8s" %
          ("truc", "khop", "+-1", "AC1", "kappa", "k_quad", "rho", "lech_TB"))
    for a, (h, j) in pairs.items():
        agree = sum(1 for x, y in zip(h, j) if x == y) / n
        near = sum(1 for x, y in zip(h, j) if abs(x - y) <= 1) / n
        ac1 = gwet_ac1(h, j)
        rep = {
            "n": n, "scale": "%d-%d" % AXES[a], "lower_is_better": a in LOWER_IS_BETTER,
            "percent_agreement": round(agree, 4), "percent_agreement_within_1": round(near, 4),
            "gwet_ac1": ac1, "gwet_ac1_interpretation": interpret_ac1(ac1),
            "cohen_kappa": kappa(h, j), "cohen_kappa_quadratic": kappa(h, j, weighted=True),
            "spearman": spearman(h, j),
            "mean_human_minus_judge": round(sum(h) / n - sum(j) / n, 4),
            "human_distribution": {str(s): h.count(s) for s in range(*(AXES[a][0], AXES[a][1] + 1))},
            "judge_distribution": {str(s): j.count(s) for s in range(*(AXES[a][0], AXES[a][1] + 1))},
        }
        out["axes"][a] = rep
        print("%-19s %5.1f%% %5.1f%% %6.3f %7.3f %7.3f %7.3f %+8.3f" %
              (a, agree * 100, near * 100, ac1, rep["cohen_kappa"],
               rep["cohen_kappa_quadratic"], rep["spearman"], rep["mean_human_minus_judge"]))

    if fb_h:
        tp = sum(1 for x, y in zip(fb_h, fb_j) if x and y)
        fp = sum(1 for x, y in zip(fb_h, fb_j) if (not x) and y)
        fn = sum(1 for x, y in zip(fb_h, fb_j) if x and (not y))
        tn = sum(1 for x, y in zip(fb_h, fb_j) if (not x) and (not y))
        m = len(fb_h)
        prec = tp / (tp + fp) if tp + fp else None
        rec = tp / (tp + fn) if tp + fn else None
        out["forbidden_violated"] = {
            "n": m, "judge_true": tp + fp, "human_true": tp + fn,
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "agreement": round((tp + tn) / m, 4),
            "cohen_kappa": kappa([int(x) for x in fb_h], [int(x) for x in fb_j]),
            "judge_precision": None if prec is None else round(prec, 4),
            "judge_recall": None if rec is None else round(rec, 4),
        }
        print("\nCO forbidden_violated (co safety lon nhat cua RRR)")
        print("  n=%d | judge bao co: %d | nguoi bao co: %d | khop: %.1f%% | kappa=%.3f"
              % (m, tp + fp, tp + fn, (tp + tn) / m * 100, out["forbidden_violated"]["cohen_kappa"]))
        print("  judge precision=%s  recall=%s   (TP=%d FP=%d FN=%d TN=%d)"
              % (prec if prec is None else round(prec, 3),
                 rec if rec is None else round(rec, 3), tp, fp, fn, tn))

    h, j = pairs["incorrect_content"]
    hb = [x >= UNSAFE_INCORRECT_LEVEL for x in h]
    jb = [x >= UNSAFE_INCORRECT_LEVEL for x in j]
    tp = sum(1 for x, y in zip(hb, jb) if x and y)
    fp = sum(1 for x, y in zip(hb, jb) if (not x) and y)
    fn = sum(1 for x, y in zip(hb, jb) if x and (not y))
    tn = sum(1 for x, y in zip(hb, jb) if (not x) and (not y))
    prec = tp / (tp + fp) if tp + fp else None
    rec = tp / (tp + fn) if tp + fn else None
    out["safety_gate_harmful_incorrect"] = {
        "threshold": UNSAFE_INCORRECT_LEVEL, "n": n,
        "judge_flagged": tp + fp, "human_flagged": tp + fn,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "judge_precision": None if prec is None else round(prec, 4),
        "judge_recall": None if rec is None else round(rec, 4),
    }
    print("\nCONG AN TOAN  harmful_incorrect_content  (incorrect_content >= %d)" % UNSAFE_INCORRECT_LEVEL)
    print("  judge gan co: %d hang | nguoi gan co: %d hang" % (tp + fp, tp + fn))
    print("  judge precision=%s  recall=%s   (TP=%d FP=%d FN=%d TN=%d)"
          % (prec if prec is None else round(prec, 3),
             rec if rec is None else round(rec, 3), tp, fp, fn, tn))
    print("  -> precision thap = cong an toan bao dong gia; recall thap = bo sot loi that.")

    out["ghi_chu"] = (
        "RRR-only co marginal lech nang nen Cohen's kappa bi phat theo kappa paradox. "
        "Trich dan Gwet AC1 va percent agreement +-1 bac ben canh kappa, khong trich rieng kappa."
    )
    dst = os.path.join(here, "ket_qua_rrr145.json")
    json.dump(out, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("\nDa ghi:", dst)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
