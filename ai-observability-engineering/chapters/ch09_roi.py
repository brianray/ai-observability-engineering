"""Chapter 9: Communicating ROI."""

from __future__ import annotations

from aiobs import Aiobs, CostLedger, Layer, MockProvider, Pillar, get_tracer
from aiobs.cost import cost_per_outcome, roi
from aiobs.instrument import set_cost_attributes

from .registry import example

CONTEXT = "Refund extensions apply only to active products purchased after March 2025"
AGENT_MINUTES_SAVED = 6.0
LOADED_HOURLY_RATE_USD = 42.0


@example(
    chapter=9,
    key="cost_per_resolution",
    title="Cost per resolution, the number a sponsor asks for",
    pillar=Pillar.ROI,
    layer=Layer.BUSINESS_AND_OUTCOMES,
    listing="9.1",
)
def cost_per_resolution() -> dict:
    """Token counts do not travel to a steering committee. This does.

    The chain is deliberately explicit: tokens to dollars, dollars to
    resolutions, resolutions to deflected labor. Every step is a place
    someone can challenge an assumption, which is the point.
    """
    tracer = get_tracer(__name__)
    provider = MockProvider()
    ledger = CostLedger()
    resolved = 0

    with tracer.start_as_current_span("quarter") as root:
        root.set_attribute(Aiobs.PILLAR, Pillar.ROI.value)
        root.set_attribute(Aiobs.LAYER, Layer.BUSINESS_AND_OUTCOMES.value)
        for i in range(200):
            reply = provider.chat(f"ticket {i}", context=CONTEXT)
            ledger.record(
                reply.model,
                reply.input_tokens,
                reply.output_tokens,
                tenant="acme",
                use_case="support",
            )
            if i % 4 != 0:  # 75% deflection rate
                resolved += 1
        root.set_attribute("aiobs.outcome.resolutions", resolved)
        set_cost_attributes(root, ledger.total_usd, tenant="acme", use_case="support")

    benefit = resolved * (AGENT_MINUTES_SAVED / 60.0) * LOADED_HOURLY_RATE_USD
    return {
        "tickets": 200,
        "resolutions": resolved,
        "total_cost_usd": ledger.total_usd,
        "cost_per_resolution_usd": cost_per_outcome(ledger, resolved),
        "modeled_benefit_usd": round(benefit, 2),
        "roi_ratio": roi(benefit, ledger.total_usd),
        "assumptions": {
            "minutes_saved_per_resolution": AGENT_MINUTES_SAVED,
            "loaded_hourly_rate_usd": LOADED_HOURLY_RATE_USD,
        },
    }


@example(
    chapter=9,
    key="unattributed_spend_gap",
    title="The share of spend nobody owns",
    pillar=Pillar.ROI,
    layer=Layer.BUSINESS_AND_OUTCOMES,
    demonstrates_failure=True,
)
def unattributed_spend_gap() -> dict:
    tracer = get_tracer(__name__)
    provider = MockProvider()
    ledger = CostLedger()

    with tracer.start_as_current_span("attribution_audit") as span:
        span.set_attribute(Aiobs.PILLAR, Pillar.ROI.value)
        span.set_attribute(Aiobs.LAYER, Layer.BUSINESS_AND_OUTCOMES.value)
        for i in range(50):
            reply = provider.chat(f"job {i}", context=CONTEXT)
            tenant = "acme" if i % 3 else "unattributed"
            ledger.record(
                reply.model, reply.input_tokens, reply.output_tokens, tenant=tenant
            )
        span.set_attribute("aiobs.cost.unattributed_share", ledger.unattributed_share())

    return {
        "total_usd": ledger.total_usd,
        "unattributed_share": ledger.unattributed_share(),
        "by_tenant": ledger.by("tenant"),
    }
