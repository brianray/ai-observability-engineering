"""Unit tests: drift detectors."""

import math
import random

import pytest

from aiobs.drift import (
    detect,
    embedding_drift_score,
    kolmogorov_smirnov,
    population_stability_index,
    top_drifting_items,
)


@pytest.fixture
def rng():
    return random.Random(20260802)


def test_identical_distributions_are_stable(rng):
    reference = [rng.gauss(0, 1) for _ in range(500)]
    current = [rng.gauss(0, 1) for _ in range(500)]
    assert population_stability_index(reference, current).verdict == "stable"
    assert kolmogorov_smirnov(reference, current).verdict == "stable"


def test_detect_flags_same_distribution_as_stable_and_shifted_distribution_as_drifted(rng):
    reference = [rng.gauss(0, 1) for _ in range(500)]
    stable = [rng.gauss(0, 1) for _ in range(500)]
    shifted = [rng.gauss(2.5, 1) for _ in range(500)]
    for method in ("psi", "ks"):
        stable_result = detect(method, reference, stable)
        shifted_result = detect(method, reference, shifted)
        assert stable_result.drifted is False
        assert stable_result.verdict == "stable"
        assert shifted_result.drifted is True
        assert shifted_result.verdict == "significant"


def test_shifted_distribution_is_flagged_by_both_detectors(rng):
    reference = [rng.gauss(0, 1) for _ in range(500)]
    current = [rng.gauss(2.5, 1) for _ in range(500)]
    for method in ("psi", "ks"):
        result = detect(method, reference, current)
        assert result.drifted
        assert result.verdict == "significant"


def test_psi_thresholds_match_same_and_shifted_windows(rng):
    reference = [rng.gauss(0, 1) for _ in range(500)]
    stable = [rng.gauss(0, 1) for _ in range(500)]
    shifted = [rng.gauss(2.5, 1) for _ in range(500)]
    assert population_stability_index(reference, stable).score < 0.10
    assert population_stability_index(reference, shifted).score > 0.25


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


def test_embedding_drift_score_is_zero_for_exact_matches():
    reference = [
        (1.0, 0.0),
        (0.0, 1.0),
        (1.0, 1.0),
        (-1.0, 0.5),
    ]
    assert embedding_drift_score(reference, reference) == 0.0


def test_embedding_drift_score_is_positive_for_rotated_embeddings():
    reference = [
        (1.0, 0.0),
        (0.8, 0.2),
        (0.0, 1.0),
        (-0.6, 0.7),
    ]
    angle = math.pi / 6
    current = [
        (
            x * math.cos(angle) - y * math.sin(angle),
            x * math.sin(angle) + y * math.cos(angle),
        )
        for x, y in reference
    ]
    assert embedding_drift_score(reference, current) > 0.0


def test_top_drifting_items_are_sorted_by_descending_distance():
    reference = [
        (1.0, 0.0),
        (0.8, 0.2),
        (0.0, 1.0),
        (-0.6, 0.7),
    ]
    current = [
        (0.7, 0.7),
        (0.5, 0.8660254),
        (-0.9, 0.1),
        (-0.8, -0.6),
    ]
    top_items = top_drifting_items(reference, current, k=3)
    distances = [distance for _, distance in top_items]
    assert all(isinstance(index, int) for index, _ in top_items)
    assert distances == sorted(distances, reverse=True)
