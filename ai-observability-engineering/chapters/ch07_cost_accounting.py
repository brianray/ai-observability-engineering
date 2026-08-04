"""Chapter 7: Accounting for AI Cost."""

from __future__ import annotations

from aiobs import Aiobs, CostLedger, Layer, MockProvider, Pillar, get_tracer
from aiobs.cost import UnknownModelError, price_call
from aiobs.instrument import set_cost_attributes, set_llm_attributes

from .registry import example

TENANTS = ("acme", "globex", "initech")
USE_CASES = ("support", "research")
CONTEXT = "Refund extensions apply only to active products purchased after March 2025"


@example(
    chapter=7,
    key="attributed_cost_ledger",
    title="Cost attributed to a tenant and a use case",
    pillar=Pillar.ROI,
    layer=Layer.BUSINESS_AND_OUTCOMES,
    listing="7.3",
)
def attributed_cost_ledger() -> dict:
    """Spend nobody can attribute is spend nobody will defend.

    The ledger records every call. Rolling up by tenant or use case is
    then arithmetic rather than an archaeology project.
    """
    tracer = get_tracer(__name__)
    provider = MockProvider()
    ledger = CostLedger()

    with tracer.start_as_current_span("billing_period") as root:
        root.set_attribute(Aiobs.PILLAR, Pillar.ROI.value)
        root.set_attribute(Aiobs.LAYER, Layer.BUSINESS_AND_OUTCOMES.value)
        for i in range(30):
            tenant = TENANTS[i % len(TENANTS)]
            use_case = USE_CASES[i % len(USE_CASES)]
            reply = provider.chat(f"request {i}", context=CONTEXT)
            record = ledger.record(
                reply.model,
                reply.input_tokens,
                reply.output_tokens,
                tenant=tenant,
                use_case=use_case,
            )
            with tracer.start_as_current_span("chat") as span:
                set_llm_attributes(
                    span,
                    provider=provider.name,
                    model=reply.model,
                    input_tokens=reply.input_tokens,
                    output_tokens=reply.output_tokens,
                )
                set_cost_attributes(span, record.usd, tenant=tenant, use_case=use_case)

    return {
        "total_usd": ledger.total_usd,
        "by_tenant": ledger.by("tenant"),
        "by_use_case": ledger.by("use_case"),
        "unattributed_share": ledger.unattributed_share(),
    }


@example(
    chapter=7,
    key="unknown_model_is_loud",
    title="An unpriced model fails loudly, not silently",
    pillar=Pillar.ROI,
    layer=Layer.BUSINESS_AND_OUTCOMES,
    listing="7.6",
)
def unknown_model_is_loud() -> dict:
    """Silently pricing an unknown model at zero is how a cost dashboard
    ends up confidently wrong. The price book raises instead."""
    tracer = get_tracer(__name__)
    with tracer.start_as_current_span("price_lookup") as span:
        span.set_attribute(Aiobs.PILLAR, Pillar.ROI.value)
        span.set_attribute(Aiobs.LAYER, Layer.BUSINESS_AND_OUTCOMES.value)
        try:
            price_call("some-model-nobody-added", 100, 100)
        except UnknownModelError as exc:
            span.set_attribute("aiobs.cost.unpriced_model", str(exc.args[0]))
            raised = True
        else:  # pragma: no cover - the point of the example is that it raises
            raised = False
    return {"raised": raised, "known_price": price_call("mock-sonnet-1", 100, 100)}
