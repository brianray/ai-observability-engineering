"""Publishing fairness metrics without publishing individuals.

Two rules do most of the work here.

**Small groups publish a sample size and nothing else.** A positive rate
over eleven people is not a statistic, it is a description of eleven
people, and at small n a "fairness dashboard" becomes a re-identification
surface. Below ``min_n`` this code publishes the count so the group's
existence stays visible, and withholds every rate.

**Gaps are computed over measurable groups only.** A suppressed group
cannot be in the max-min, because its rate was never computed. Including
it as a zero is how a suppression rule turns into a fabricated disparity.

The four gauges are the chapter's published set. Their label sets are
fixed: a gauge whose labels vary between releases breaks every recorded
rule built on it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

#: Below this, rates are withheld. 50 is a defensible floor for the
#: book's example, not a regulatory threshold. Yours comes from your own
#: disclosure-control review; see the SME REVIEW box in Section 13.4.
DEFAULT_MIN_N = 50

#: The four gauges this chapter publishes, with their label sets.
GAUGE_LABELS: dict[str, tuple[str, ...]] = {
    "aiobs_fairness_positive_rate": ("group",),
    "aiobs_fairness_sample_size": ("group",),
    "aiobs_fairness_parity_gap": (),
    "aiobs_fairness_equalized_odds_gap": (),
}


@dataclass(frozen=True)
class GroupOutcomes:
    """Confusion-matrix counts for one group."""

    group: str
    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int

    @property
    def n(self) -> int:
        return (
            self.true_positives
            + self.false_positives
            + self.true_negatives
            + self.false_negatives
        )

    @property
    def positive_rate(self) -> float:
        """Share of the group receiving a positive decision."""
        return (self.true_positives + self.false_positives) / self.n if self.n else 0.0

    @property
    def true_positive_rate(self) -> float | None:
        actual_positives = self.true_positives + self.false_negatives
        if actual_positives == 0:
            return None
        return self.true_positives / actual_positives

    @property
    def false_positive_rate(self) -> float | None:
        actual_negatives = self.false_positives + self.true_negatives
        if actual_negatives == 0:
            return None
        return self.false_positives / actual_negatives


class GaugeRecorder:
    """Where gauges go.

    An in-memory recorder by default so the chapter runs in CI with no
    Prometheus client installed; ``prometheus_client`` is an optional
    extra. Tests assert against what was recorded, which is the thing
    that actually matters, rather than against a scrape endpoint.
    """

    def __init__(self) -> None:
        self.samples: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}

    def set(self, name: str, value: float, **labels: str) -> None:
        expected = GAUGE_LABELS.get(name)
        if expected is None:
            raise KeyError(f"{name!r} is not one of the published gauges")
        if tuple(sorted(labels)) != tuple(sorted(expected)):
            raise ValueError(
                f"{name} expects labels {expected}, got {tuple(sorted(labels))}. "
                "A gauge whose labels move breaks every rule built on it."
            )
        self.samples[(name, tuple(sorted(labels.items())))] = value

    def get(self, name: str, **labels: str) -> float | None:
        return self.samples.get((name, tuple(sorted(labels.items()))))

    def names(self) -> set[str]:
        return {name for name, _ in self.samples}


@dataclass(frozen=True)
class FairnessReport:
    measurable_groups: tuple[str, ...]
    suppressed_groups: tuple[str, ...]
    positive_rates: Mapping[str, float]
    parity_gap: float
    equalized_odds_gap: float
    tpr_gap: float
    fpr_gap: float


def _spread(values: list[float]) -> float:
    return round(max(values) - min(values), 10) if len(values) >= 2 else 0.0


def publish_fairness(
    groups: list[GroupOutcomes],
    recorder: GaugeRecorder | None = None,
    *,
    min_n: int = DEFAULT_MIN_N,
) -> tuple[FairnessReport, GaugeRecorder]:
    """Compute and publish the four gauges."""
    recorder = recorder or GaugeRecorder()

    measurable = [g for g in groups if g.n >= min_n]
    suppressed = [g for g in groups if g.n < min_n]

    # Every group publishes its sample size, including suppressed ones.
    # A group that vanishes from the dashboard entirely is a group nobody
    # notices is missing.
    for group in groups:
        recorder.set("aiobs_fairness_sample_size", float(group.n), group=group.group)

    positive_rates = {}
    for group in measurable:
        rate = round(group.positive_rate, 10)
        positive_rates[group.group] = rate
        recorder.set("aiobs_fairness_positive_rate", rate, group=group.group)

    parity_gap = _spread(list(positive_rates.values()))

    tprs = [g.true_positive_rate for g in measurable if g.true_positive_rate is not None]
    fprs = [g.false_positive_rate for g in measurable if g.false_positive_rate is not None]
    tpr_gap = _spread(tprs)
    fpr_gap = _spread(fprs)
    # Equalized odds is violated by the worse of the two, not their mean:
    # averaging lets a large TPR gap hide behind a small FPR gap.
    equalized_odds_gap = max(tpr_gap, fpr_gap)

    recorder.set("aiobs_fairness_parity_gap", parity_gap)
    recorder.set("aiobs_fairness_equalized_odds_gap", equalized_odds_gap)

    return (
        FairnessReport(
            measurable_groups=tuple(g.group for g in measurable),
            suppressed_groups=tuple(g.group for g in suppressed),
            positive_rates=positive_rates,
            parity_gap=parity_gap,
            equalized_odds_gap=equalized_odds_gap,
            tpr_gap=tpr_gap,
            fpr_gap=fpr_gap,
        ),
        recorder,
    )
