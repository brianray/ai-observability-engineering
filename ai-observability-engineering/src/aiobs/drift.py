"""Drift detection (Chapter 6).

Two estimators, both dependency-free, both on the same interface so a
chapter example can swap one for the other and show the difference:

* Population Stability Index, the workhorse for binned distributions.
* Two-sample Kolmogorov-Smirnov, for continuous distributions where you
  do not want to pick bins.

Neither tells you a system is broken. They tell you the input or output
distribution has moved relative to a reference window, which is the
question a drift alert is actually answering.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

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
    ref = sorted(reference)
    cur = sorted(current)
    n, m = len(ref), len(cur)

    merged = sorted(set(ref) | set(cur))

    def ecdf(sample: list[float], x: float) -> float:
        lo, hi = 0, len(sample)
        while lo < hi:
            mid = (lo + hi) // 2
            if sample[mid] <= x:
                lo = mid + 1
            else:
                hi = mid
        return lo / len(sample)

    statistic = max(abs(ecdf(ref, x) - ecdf(cur, x)) for x in merged)
    critical = math.sqrt(-0.5 * math.log(alpha / 2)) * math.sqrt((n + m) / (n * m))

    if statistic < critical:
        verdict: Verdict = "stable"
    elif statistic < critical * 1.5:
        verdict = "moderate"
    else:
        verdict = "significant"

    return DriftResult("ks", round(statistic, 6), verdict, n, m)


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
