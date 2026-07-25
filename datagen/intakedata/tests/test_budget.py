from datagen.intakedata.config import CASE_TYPE_TARGETS, FULL_TARGET, compute_budget


def test_case_quota_sum_is_exact() -> None:
    assert len(CASE_TYPE_TARGETS) == 16
    assert sum(CASE_TYPE_TARGETS.values()) == FULL_TARGET == 4_000


def test_largest_remainder_budget_is_deterministic_and_exact() -> None:
    assert compute_budget(0) == {case: 0 for case in CASE_TYPE_TARGETS}
    for total in (1, 8, 16, 57, 985, FULL_TARGET):
        first = compute_budget(total)
        assert first == compute_budget(total)
        assert sum(first.values()) == total
        assert set(first) == set(CASE_TYPE_TARGETS)
        assert all(value >= 0 for value in first.values())


def test_budget_rejects_invalid_total() -> None:
    try:
        compute_budget(-1)
    except ValueError as exc:
        assert "non-negative" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("negative total must fail")
