import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluation.analysis.stats import (
    cliffs_delta, holm_bonferroni, mcnemar_exact, paired_bootstrap,
    wilcoxon_signed_rank, win_tie_loss,
)


def test_paired_bootstrap_detects_clear_difference():
    a = [1.0] * 50
    b = [0.0] * 50
    res = paired_bootstrap(a, b, n_resamples=2000)
    assert res["significant"] is True
    assert res["mean_diff"] == 1.0


def test_paired_bootstrap_null():
    a = [float(i % 2) for i in range(100)]
    res = paired_bootstrap(a, a, n_resamples=2000)
    assert res["mean_diff"] == 0.0
    assert res["significant"] is False


def test_wilcoxon_direction():
    a = [3.0 + 0.01 * i for i in range(30)]
    b = [x - 1.0 for x in a]
    res = wilcoxon_signed_rank(a, b)
    assert res["p_value"] is not None and res["p_value"] < 0.01


def test_wilcoxon_small_n_warns():
    assert wilcoxon_signed_rank([1.0, 2.0], [2.0, 1.0])["p_value"] is None


def test_mcnemar():
    a = [True] * 20 + [False] * 5
    b = [True] * 25
    res = mcnemar_exact(a, b)
    assert res["n01"] == 5 and res["n10"] == 0
    assert res["p_value"] < 0.1


def test_mcnemar_no_discordant():
    assert mcnemar_exact([True, False], [True, False])["p_value"] == 1.0


def test_holm():
    out = holm_bonferroni({"x": 0.001, "y": 0.04, "z": 0.9})
    assert out["x"]["significant"] is True
    assert out["z"]["significant"] is False


def test_cliffs_delta_bounds():
    assert cliffs_delta([1, 1], [0, 0]) == 1.0
    assert cliffs_delta([0, 0], [1, 1]) == -1.0


def test_win_tie_loss():
    assert win_tie_loss([1, 2, 3], [1, 1, 4]) == {"win": 1, "tie": 1, "loss": 1}
