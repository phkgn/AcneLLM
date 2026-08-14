from evaluation.metrics.intake import (
    canonicalization_hit,
    enum_validity,
    expected_calibration_error,
    negation_leak,
)


def test_enum_validity_counts_only_emitted_values():
    result = enum_validity(["oily", "invented", None], {"oily", "dry"})
    assert result == {"rate": 0.5, "valid": 1, "invalid": 1, "n": 2}


def test_expected_calibration_error_uses_equal_width_bins():
    assert expected_calibration_error([0.1, 0.9], [False, True]) == 0.1


def test_negation_leak_counts_values_and_affected_samples():
    result = negation_leak([({"BHA"}, {"BHA"}), ({"retinol"}, set())])
    assert result["rate"] == 0.5
    assert result["leaked"] == 1
    assert result["affected_samples"] == 1


def test_canonicalization_hit_requires_exact_canonical_value():
    result = canonicalization_hit(
        [("salicylic acid", "salicylic acid"), ("adapalene", "Differin")]
    )
    assert result == {"rate": 0.5, "hits": 1, "n": 2}
