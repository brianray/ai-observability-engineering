"""Cost accounting and ROI attribution (Part III, Chapters 7-9).

Chapter 1 notes that cost and capacity scale with tokens, not requests.
This module is the smallest honest version of that accounting: a price
book, a per-call cost, and roll-ups by whatever dimension the business
actually cares about.

The book's architectural point, made in Chapter 2 and again in Part III:
telemetry pipelines that sample are fine for latency and useless for
cost. A sampled trace stream cannot be a system of record for spend.
``CostLedger`` therefore records every call, not a sample.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

#: USD per 1,000 tokens. Illustrative figures; refresh before quoting.
PRICE_BOOK: dict[str, tuple[float, float]] = {
    "mock-sonnet-1": (0.003, 0.015),
    "mock-haiku-1": (0.0008, 0.004),
    "mock-opus-1": (0.015, 0.075),
}


class UnknownModelError(KeyError):
    """Raised when a model has no entry in the price book.

    Deliberately loud. Silently pricing an unknown model at zero is how a
    cost dashboard ends up confidently wrong.
    """


def price_call(model: str, input_tokens: int, output_tokens: int) -> float:
    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("token counts must be non-negative")
    try:
        in_price, out_price = PRICE_BOOK[model]
    except KeyError as exc:
        raise UnknownModelError(model) from exc
    return input_tokens / 1000.0 * in_price + output_tokens / 1000.0 * out_price


@dataclass(frozen=True)
class CostRecord:
    model: str
    input_tokens: int
    output_tokens: int
    usd: float
    tenant: str = "unattributed"
    use_case: str = "unattributed"
    trace_id: str = ""


@dataclass
class CostLedger:
    """Append-only record of every priced call."""

    records: list[CostRecord] = field(default_factory=list)

    def record(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        *,
        tenant: str = "unattributed",
        use_case: str = "unattributed",
        trace_id: str = "",
    ) -> CostRecord:
        entry = CostRecord(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            usd=price_call(model, input_tokens, output_tokens),
            tenant=tenant,
            use_case=use_case,
            trace_id=trace_id,
        )
        self.records.append(entry)
        return entry

    @property
    def total_usd(self) -> float:
        return round(sum(r.usd for r in self.records), 6)

    @property
    def total_tokens(self) -> int:
        return sum(r.input_tokens + r.output_tokens for r in self.records)

    def by(self, dimension: str) -> dict[str, float]:
        if dimension not in {"model", "tenant", "use_case"}:
            raise ValueError(f"cannot roll up by {dimension!r}")
        totals: dict[str, float] = defaultdict(float)
        for r in self.records:
            totals[getattr(r, dimension)] += r.usd
        return {k: round(v, 6) for k, v in sorted(totals.items())}

    def unattributed_share(self) -> float:
        """Fraction of spend that cannot be assigned to a tenant.

        The number every FinOps conversation about GenAI starts with.
        """
        if not self.records:
            return 0.0
        unattributed = sum(r.usd for r in self.records if r.tenant == "unattributed")
        return round(unattributed / self.total_usd, 6) if self.total_usd else 0.0


def roi(benefit_usd: float, cost_usd: float) -> float:
    """Return on investment as a ratio. Raises on a zero cost basis."""
    if cost_usd <= 0:
        raise ValueError("cost basis must be positive")
    return round((benefit_usd - cost_usd) / cost_usd, 6)


def cost_per_outcome(ledger: CostLedger, successful_outcomes: int) -> float:
    """The number a business sponsor actually asks for."""
    if successful_outcomes <= 0:
        raise ValueError("successful_outcomes must be positive")
    return round(ledger.total_usd / successful_outcomes, 6)


def summarize(ledgers: Iterable[CostLedger]) -> Mapping[str, float]:
    total = sum(ledger.total_usd for ledger in ledgers)
    return {"total_usd": round(total, 6)}
