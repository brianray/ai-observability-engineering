"""Chapter 8: a reconciled, fully loaded cost per acceptable answer.

The point of this example is not that token spend matters less. It is that
token spend alone is not the invoice. Capacity reservations, storage,
evaluation overhead, and human review are all part of the delivered cost of
an answer that actually passed the quality bar.
"""

from __future__ import annotations

import json
from pathlib import Path

from aiobs import Aiobs, Layer, Pillar, get_tracer
from aiobs.instrument import set_cost_attributes

from ..registry import example

_FIXTURE_PATH = Path(__file__).with_name("fixtures") / "cost_ledger.json"
_PURPOSES = {"judge", "guardrail"}


def _load_fixture() -> dict[str, object]:
    return json.loads(_FIXTURE_PATH.read_text())


def _sum_usd(rows: list[dict[str, object]]) -> float:
    return round(sum(float(row["usd"]) for row in rows), 6)


@example(
    chapter=8,
    key="fully_loaded_cost_per_acceptable_answer",
    title="The fully loaded cost of one acceptable answer",
    pillar=Pillar.ROI,
    layer=Layer.APPLICATION_AND_ORCHESTRATION,
    listing="8.4",
)
def fully_loaded_cost_per_acceptable_answer(window: str = "2025-06") -> dict:
    """Price the answer the business accepted, not only the model call."""
    payload = _load_fixture()
    windows = payload.get("windows", {})
    if not isinstance(windows, dict) or window not in windows:
        raise ValueError(f"no cost ledger fixture data for window {window!r}")

    entry = windows[window]
    if not isinstance(entry, dict):
        raise ValueError(f"ledger fixture for window {window!r} is malformed")

    model_spend_rows = list(entry.get("model_spend_rows", []))
    purpose_spend_rows = list(entry.get("purpose_spend_rows", []))
    storage_rows = list(entry.get("storage_cost_rows", []))
    provisioned_capacity_rows = list(entry.get("provisioned_capacity_rows", []))
    review_hours = float(entry.get("review_hours", 0.0))
    loaded_rate = float(entry.get("loaded_rate_usd_per_hour", 0.0))
    passing_answers = int(entry.get("passing_answers", 0))

    if passing_answers <= 0:
        raise ValueError(
            f"window {window!r} has zero eval-passing answers; cannot compute "
            "fully loaded cost per acceptable answer"
        )

    model_spend_usd = _sum_usd(model_spend_rows)
    provisioned_capacity_usd = _sum_usd(provisioned_capacity_rows)
    judge_guardrail_spend_usd = round(
        sum(
            float(row["usd"])
            for row in purpose_spend_rows
            if row.get("purpose") in _PURPOSES
        ),
        6,
    )
    storage_usd = _sum_usd(storage_rows)
    review_labor_usd = round(review_hours * loaded_rate, 6)
    total_cost_usd = round(
        model_spend_usd
        + provisioned_capacity_usd
        + judge_guardrail_spend_usd
        + storage_usd
        + review_labor_usd,
        6,
    )
    per_answer_usd = round(total_cost_usd / passing_answers, 6)

    tracer = get_tracer(__name__)
    with tracer.start_as_current_span("fully_loaded_cost_per_acceptable_answer") as span:
        span.set_attribute(Aiobs.PILLAR, Pillar.ROI.value)
        span.set_attribute(Aiobs.LAYER, Layer.APPLICATION_AND_ORCHESTRATION.value)
        set_cost_attributes(span, total_cost_usd, tenant="acme", use_case="support")
        with tracer.start_as_current_span("judge_guardrail_subtotal") as subtotal:
            subtotal.set_attribute(Aiobs.PURPOSE, sorted(_PURPOSES))

    return {
        "window": window,
        "model_spend_usd": model_spend_usd,
        "provisioned_capacity_usd": provisioned_capacity_usd,
        "judge_guardrail_spend_usd": judge_guardrail_spend_usd,
        "storage_usd": storage_usd,
        "review_hours": review_hours,
        "loaded_rate_usd_per_hour": loaded_rate,
        "review_labor_usd": review_labor_usd,
        "passing_answers": passing_answers,
        "total_cost_usd": total_cost_usd,
        "fully_loaded_cost_per_acceptable_answer_usd": per_answer_usd,
    }
