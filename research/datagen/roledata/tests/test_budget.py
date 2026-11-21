from datagen.roledata.config import CASE_TYPE_TARGETS, FULL_TARGET, compute_budget


def test_full_budget_is_exact_plan_table() -> None:
    budget = compute_budget(FULL_TARGET)
    assert budget == CASE_TYPE_TARGETS
    assert sum(budget.values()) == 3_500


def test_largest_remainder_preserves_arbitrary_total() -> None:
    for total in (0, 1, 8, 16, 101, 3_499):
        budget = compute_budget(total)
        assert sum(budget.values()) == total
        assert set(budget) == set(CASE_TYPE_TARGETS)
        assert all(value >= 0 for value in budget.values())


def test_negative_budget_is_rejected() -> None:
    try:
        compute_budget(-1)
    except ValueError as exc:
        assert "non-negative" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("negative total was accepted")
