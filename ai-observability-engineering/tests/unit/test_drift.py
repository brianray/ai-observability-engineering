"""Unit tests: drift detectors."""

import random

import pytest

from aiobs.drift import detect, kolmogorov_smirnov, population_stability_index


@pytest.fixture
def rng():
    return random.Random(20260802)


def test_identical_distributions_are_stable(rng):
    reference = [rng.gauss(0, 1) for _ in range(500)]
    current = [rng.gauss(0, 1) for _ in range(500)]
    assert population_stability_index(reference, current).verdict == "stable"
    assert kolmogorov_smirnov(reference, current).verdict == "stable"


def test_shifted_distribution_is_flagged_by_both_detectors(rng):
    reference = [rng.gauss(0, 1) for _ in range(500)]
    current = [rng.gauss(2.5, 1) for _ in range(500)]
    for method in ("psi", "ks"):
        result = detect(method, reference, current)
        assert result.drifted
        assert result.verdict == "significant"


def test_psi_grows_monotonically_with_the_shift(rng):
    reference = [rng.gauss(0, 1) for _ in range(800)]
    scores = [
        population_stability_index(reference, [rng.gauss(shift, 1) for _ in range(800)]).score
        for shift in (0.2, 0.8, 2.0)
    ]
    assert scores == sorted(scores)


def test_empty_bins_do_not_produce_infinities(rng):
    """Laplace smoothing: an empty bin must not blow up the PSI."""
    reference = [rng.gauss(0, 1) for _ in range(200)]
    current = [5.0] * 200
    result = population_stability_index(reference, current)
    assert result.score == result.score  # not NaN
    assert result.score < float("inf")


def test_zero_variance_reference_is_rejected():
    """Say so rather than returning a confident zero."""
    with pytest.raises(ValueError, match="zero variance"):
        population_stability_index([0.5] * 100, [0.1, 0.9] * 50)


def test_tiny_windows_rejected():
    with pytest.raises(ValueError):
        detect("psi", [1.0], [2.0])


def test_unknown_method_rejected():
    with pytest.raises(ValueError, match="unknown drift method"):
        detect("vibes", [1.0, 2.0, 3.0], [1.0, 2.0, 3.0])


def test_result_carries_window_sizes(rng):
    reference = [rng.random() for _ in range(120)]
    current = [rng.random() for _ in range(90)]
    result = detect("ks", reference, current)
    assert (result.reference_size, result.current_size) == (120, 90)
