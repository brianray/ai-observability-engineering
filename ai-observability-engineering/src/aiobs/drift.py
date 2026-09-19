"""Drift detection (Chapter 6).

These detectors answer a narrow operational question: did the current
window move relative to the reference one? PSI does that for binned
distributions, KS does it for continuous distributions, and embedding
drift does it by asking whether each current vector still has a close
nearest-neighbor match in the reference set.

None of them prove a system is broken. They quantify movement so the
rest of the monitoring stack can decide what that movement means.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from scipy.stats import ks_2samp  # type: ignore[import-untyped]
from sklearn.neighbors import NearestNeighbors  # type: ignore[import-untyped]

Verdict = Literal["stable", "moderate", "significant"]

#: Conventional PSI thresholds. Not laws of nature; tune per system.
PSI_MODERATE = 0.10
PSI_SIGNIFICANT = 0.25


@dataclass(frozen=True)
class DriftResult:
    method: str
    score: float
    verdict: Verdict
    reference_size: int
    current_size: int

    @property
    def drifted(self) -> bool:
        return self.verdict != "stable"


def _validate(reference: Sequence[float], current: Sequence[float]) -> None:
    if len(reference) < 2 or len(current) < 2:
        raise ValueError("both windows need at least two observations")


def _embedding_windows(
    reference: Sequence[Sequence[float]],
    current: Sequence[Sequence[float]],
) -> tuple[list[list[float]], list[list[float]]]:
    if not reference or not current:
        raise ValueError("both embedding windows need at least one vector")

    ref_vectors = [list(vector) for vector in reference]
    cur_vectors = [list(vector) for vector in current]
    width = len(ref_vectors[0])
    if width == 0:
        raise ValueError("embedding vectors must not be empty")

    for vectors in (ref_vectors, cur_vectors):
        if any(len(vector) != width for vector in vectors):
            raise ValueError("embedding vectors must all share the same dimensionality")

    return ref_vectors, cur_vectors


def _nearest_neighbor_distances(
    reference: Sequence[Sequence[float]],
    current: Sequence[Sequence[float]],
) -> list[float]:
    ref_vectors, cur_vectors = _embedding_windows(reference, current)
    neighbors = NearestNeighbors(metric="cosine", n_neighbors=1)
    neighbors.fit(ref_vectors)
    distances, _ = neighbors.kneighbors(cur_vectors)
    return [
        0.0 if math.isclose(float(distance[0]), 0.0, abs_tol=1e-12) else float(distance[0])
        for distance in distances
    ]


def population_stability_index(
    reference: Sequence[float],
    current: Sequence[float],
    bins: int = 10,
) -> DriftResult:
    _validate(reference, current)
    if bins < 2:
        raise ValueError("bins must be >= 2")

    lo, hi = min(reference), max(reference)
    if math.isclose(lo, hi):
        # A degenerate reference window cannot support binning. Say so
        # rather than returning a confident zero.
        raise ValueError("reference window has zero variance")

    width = (hi - lo) / bins
    edges = [lo + i * width for i in range(bins + 1)]
    edges[-1] = math.inf
    edges[0] = -math.inf

    def histogram(values: Sequence[float]) -> list[float]:
        counts = [0] * bins
        for v in values:
            for i in range(bins):
                if edges[i] <= v < edges[i + 1]:
                    counts[i] += 1
                    break
        total = len(values)
        # Laplace smoothing keeps empty bins from producing infinities.
        return [(c + 0.5) / (total + 0.5 * bins) for c in counts]

    ref_pct = histogram(reference)
    cur_pct = histogram(current)
    psi = sum((c - r) * math.log(c / r) for r, c in zip(ref_pct, cur_pct, strict=True))
    psi = round(psi, 6)

    if psi < PSI_MODERATE:
        verdict: Verdict = "stable"
    elif psi < PSI_SIGNIFICANT:
        verdict = "moderate"
    else:
        verdict = "significant"

    return DriftResult("psi", psi, verdict, len(reference), len(current))


def kolmogorov_smirnov(
    reference: Sequence[float],
    current: Sequence[float],
    alpha: float = 0.05,
) -> DriftResult:
    _validate(reference, current)
    result = ks_2samp(reference, current)
    statistic = round(float(result.statistic), 6)

    if result.pvalue >= alpha:
        verdict: Verdict = "stable"
    elif result.pvalue >= alpha / 10:
        verdict = "moderate"
    else:
        verdict = "significant"

    return DriftResult("ks", statistic, verdict, len(reference), len(current))


def embedding_drift_score(
    reference: Sequence[Sequence[float]],
    current: Sequence[Sequence[float]],
) -> float:
    """Aggregate per-item nearest-neighbor drift for embedding windows.

    Chapter 6 treats embedding drift as a retrieval-style question:
    does each current item still have a close analogue in the reference
    set? Using the nearest neighbor preserves that per-item perspective.
    Averaging every pairwise similarity would dilute the signal and turn
    a local mismatch into a global blur.
    """

    distances = _nearest_neighbor_distances(reference, current)
    score = sum(distances) / len(distances)
    return 0.0 if math.isclose(score, 0.0, abs_tol=1e-12) else round(score, 6)


def top_drifting_items(
    reference: Sequence[Sequence[float]],
    current: Sequence[Sequence[float]],
    k: int = 5,
) -> list[tuple[int, float]]:
    """Return the current items whose nearest-neighbor match degraded most.

    A single score is useful for alerting, but incident response needs to
    know which specific items moved furthest from the reference window so
    an owner can inspect them directly.
    """

    if k <= 0:
        return []

    distances = _nearest_neighbor_distances(reference, current)
    ranked = sorted(
        enumerate(distances),
        key=lambda item: item[1],
        reverse=True,
    )
    return [(index, round(distance, 6)) for index, distance in ranked[:k]]


DETECTORS = {
    "psi": population_stability_index,
    "ks": kolmogorov_smirnov,
}


def detect(method: str, reference: Sequence[float], current: Sequence[float]) -> DriftResult:
    try:
        detector = DETECTORS[method]
    except KeyError as exc:
        raise ValueError(f"unknown drift method: {method!r}") from exc
    return detector(reference, current)
