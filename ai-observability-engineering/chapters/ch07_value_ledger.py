"""Chapter 7: Value ledgers and ROI narratives."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from aiobs import Aiobs, Layer, Pillar, get_tracer
from aiobs.cost import roi

from .registry import example


@dataclass(frozen=True)
class ValueEntry:
    kind: str
    label: str
    amount_usd: float
    confidence: str


@dataclass
class AIValueLedger:
    """A small ledger that keeps cost and value claims separate."""

    entries: list[ValueEntry] = field(default_factory=list)

    def add_cost(
        self, label: str, amount_usd: float, *, confidence: str = "direct_cost"
    ) -> ValueEntry:
        return self._add("cost", label, amount_usd, confidence)

    def add_benefit(self, label: str, amount_usd: float, *, confidence: str) -> ValueEntry:
        if confidence == "direct_cost":
            raise ValueError("direct_cost is reserved for cost entries")
        return self._add("benefit", label, amount_usd, confidence)

    def _add(self, kind: str, label: str, amount_usd: float, confidence: str) -> ValueEntry:
        if amount_usd < 0:
            raise ValueError("amount_usd must be non-negative")
        if not confidence:
            raise ValueError("confidence must be non-empty")
        entry = ValueEntry(
            kind=kind,
            label=label,
            amount_usd=round(float(amount_usd), 2),
            confidence=confidence,
        )
        self.entries.append(entry)
        return entry

    def costs(self) -> float:
        return round(sum(entry.amount_usd for entry in self.entries if entry.kind == "cost"), 2)

    def benefits(self) -> float:
        return round(
            sum(entry.amount_usd for entry in self.entries if entry.kind == "benefit"),
            2,
        )

    def roi(self) -> float:
        return roi(self.benefits(), self.costs())

    def by_confidence(self) -> dict[str, float]:
        totals: dict[str, float] = defaultdict(float)
        for entry in self.entries:
            totals[entry.confidence] += entry.amount_usd
        return {key: round(value, 2) for key, value in sorted(totals.items())}

    def without_confidence(self, *labels: str) -> AIValueLedger:
        blocked = set(labels)
        return AIValueLedger(
            [entry for entry in self.entries if entry.confidence not in blocked]
        )


def table_7_3_ledger() -> AIValueLedger:
    ledger = AIValueLedger()
    ledger.add_cost("Platform and model spend", 54000)
    ledger.add_cost("Integration engineering", 17000)
    ledger.add_cost("Evaluation and oversight", 9000)
    ledger.add_benefit("Deflected support labor", 62400, confidence="measured")
    ledger.add_benefit("Faster assisted resolutions", 37300, confidence="measured")
    ledger.add_benefit("Cross-sell uplift", 15000, confidence="assumed")
    return ledger


def ledger_to_markdown(ledger: AIValueLedger) -> str:
    lines = [
        "| Entry | Type | Confidence | Amount (USD) |",
        "| --- | --- | --- | ---: |",
    ]
    for entry in ledger.entries:
        lines.append(
            f"| {entry.label} | {entry.kind} | {entry.confidence} | {entry.amount_usd:,.2f} |"
        )
    lines.extend(
        [
            f"| **Total costs** |  |  | **{ledger.costs():,.2f}** |",
            f"| **Total benefits** |  |  | **{ledger.benefits():,.2f}** |",
            f"| **ROI** |  |  | **{ledger.roi():.2f}** |",
        ]
    )
    return "\n".join(lines)


def ledger_summary_metrics(ledger: AIValueLedger) -> dict[str, float | str]:
    """Executive-summary metrics derived from Table 7.3."""
    without_assumed = ledger.without_confidence("assumed")
    by_confidence = ledger.by_confidence()
    return {
        "costs_usd": ledger.costs(),
        "benefits_usd": ledger.benefits(),
        "roi_ratio": ledger.roi(),
        "roi_without_assumed": without_assumed.roi(),
        "assumed_value_usd": by_confidence.get("assumed", 0.0),
        "ledger_markdown": ledger_to_markdown(ledger),
    }


def ledger_targets_from_ch07(
    ledger: AIValueLedger | None = None,
) -> dict[str, dict[str, float | str]]:
    """Targets derived from the Chapter 7 ledger, not restated inline."""
    summary = ledger_summary_metrics(ledger or table_7_3_ledger())
    return {
        "roi_ratio": {
            "target": float(summary["roi_without_assumed"]),
            "goal": "at_least",
            "source": "Chapter 7 Table 7.3 measured-only ROI floor",
        },
        "assumed_value_usd": {
            "target": float(summary["assumed_value_usd"]),
            "goal": "at_most",
            "source": "Chapter 7 Table 7.3 assumed-value cap",
        },
    }


@example(
    chapter=7,
    key="value_ledger",
    title="A value ledger that separates measured from assumed value",
    pillar=Pillar.ROI,
    layer=Layer.BUSINESS_AND_OUTCOMES,
    listing="7.1",
)
def value_ledger() -> dict:
    """Keep direct costs separate from measured and assumed value."""
    tracer = get_tracer(__name__)
    ledger = table_7_3_ledger()

    with tracer.start_as_current_span("value_ledger") as span:
        span.set_attribute(Aiobs.PILLAR, Pillar.ROI.value)
        span.set_attribute(Aiobs.LAYER, Layer.BUSINESS_AND_OUTCOMES.value)
        span.set_attribute("aiobs.value.costs_usd", ledger.costs())
        span.set_attribute("aiobs.value.benefits_usd", ledger.benefits())
        span.set_attribute("aiobs.value.assumed_usd", ledger.by_confidence()["assumed"])

    without_assumed = ledger.without_confidence("assumed")
    return {
        "costs_usd": ledger.costs(),
        "benefits_usd": ledger.benefits(),
        "roi_ratio": ledger.roi(),
        "roi_without_assumed": without_assumed.roi(),
        "by_confidence": ledger.by_confidence(),
        "markdown": ledger_to_markdown(ledger),
    }


@example(
    chapter=7,
    key="cost_per_outcome_equivalents",
    title="Cost per outcome translated into outcome equivalents",
    pillar=Pillar.ROI,
    layer=Layer.BUSINESS_AND_OUTCOMES,
    listing="7.2",
)
def cost_per_outcome_equivalents() -> dict:
    """Translate total spend into the unit a sponsor actually buys."""
    tracer = get_tracer(__name__)
    ledger = AIValueLedger()
    ledger.add_cost("Program spend", 50020)
    outcome_equivalents = 12200
    cost_per_outcome_usd = round(ledger.costs() / outcome_equivalents, 2)

    with tracer.start_as_current_span("cost_per_outcome_equivalents") as span:
        span.set_attribute(Aiobs.PILLAR, Pillar.ROI.value)
        span.set_attribute(Aiobs.LAYER, Layer.BUSINESS_AND_OUTCOMES.value)
        span.set_attribute("aiobs.outcome.equivalents", outcome_equivalents)
        span.set_attribute("aiobs.cost_per_outcome_usd", cost_per_outcome_usd)

    return {
        "total_cost_usd": ledger.costs(),
        "outcome_equivalents": outcome_equivalents,
        "cost_per_outcome_usd": cost_per_outcome_usd,
        "display": {
            "outcome_equivalents": f"{outcome_equivalents:,}",
            "cost_per_outcome_usd": f"${cost_per_outcome_usd:.2f}",
        },
    }
