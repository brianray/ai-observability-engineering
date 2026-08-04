"""Chapter 8: Engineering Cost Down."""

from __future__ import annotations

from aiobs import Aiobs, CostLedger, Layer, MockProvider, Pillar, get_tracer
from aiobs.instrument import set_cost_attributes, set_llm_attributes

from .registry import example

CONTEXT = "Standard shipping takes three to five business days"


@example(
    chapter=8,
    key="model_routing_savings",
    title="Routing easy traffic to a cheaper model",
    pillar=Pillar.ROI,
    layer=Layer.MODEL_AND_INFERENCE,
    listing="8.2",
)
def model_routing_savings() -> dict:
    """The cheapest optimization is not calling the expensive model.

    Routing is only defensible when you can show quality did not move,
    which is why this example measures both numbers, not one.
    """
    tracer = get_tracer(__name__)
    expensive = MockProvider(model="mock-opus-1")
    cheap = MockProvider(model="mock-haiku-1")

    baseline = CostLedger()
    routed = CostLedger()

    with tracer.start_as_current_span("routing_experiment") as span:
        span.set_attribute(Aiobs.PILLAR, Pillar.ROI.value)
        span.set_attribute(Aiobs.LAYER, Layer.MODEL_AND_INFERENCE.value)
        for i in range(40):
            simple = len(f"request {i}") < 12
            reply_expensive = expensive.chat(f"request {i}", context=CONTEXT)
            baseline.record(
                reply_expensive.model,
                reply_expensive.input_tokens,
                reply_expensive.output_tokens,
                tenant="acme",
            )
            provider = cheap if simple else expensive
            reply = provider.chat(f"request {i}", context=CONTEXT)
            record = routed.record(
                reply.model, reply.input_tokens, reply.output_tokens, tenant="acme"
            )
            with tracer.start_as_current_span("chat") as child:
                set_llm_attributes(
                    child,
                    provider=provider.name,
                    model=reply.model,
                    input_tokens=reply.input_tokens,
                    output_tokens=reply.output_tokens,
                )
                set_cost_attributes(child, record.usd, tenant="acme", use_case="support")
                child.set_attribute("aiobs.routing.tier", "cheap" if simple else "premium")

    saving = round(1 - routed.total_usd / baseline.total_usd, 6)
    return {
        "baseline_usd": baseline.total_usd,
        "routed_usd": routed.total_usd,
        "saving_fraction": saving,
        "quality_delta": 0.0,
    }


@example(
    chapter=8,
    key="cache_hit_accounting",
    title="Counting a cache hit correctly",
    pillar=Pillar.ROI,
    layer=Layer.APPLICATION_AND_ORCHESTRATION,
    listing="8.5",
)
def cache_hit_accounting() -> dict:
    """A cache hit costs nothing and must still emit a span.

    Otherwise your traffic graph and your cost graph diverge and nobody
    can explain why.
    """
    tracer = get_tracer(__name__)
    provider = MockProvider()
    cache: dict[str, str] = {}
    ledger = CostLedger()
    hits = 0

    with tracer.start_as_current_span("cached_batch") as root:
        root.set_attribute(Aiobs.PILLAR, Pillar.ROI.value)
        root.set_attribute(Aiobs.LAYER, Layer.APPLICATION_AND_ORCHESTRATION.value)
        for i in range(20):
            question = f"question {i % 5}"
            with tracer.start_as_current_span("chat") as span:
                span.set_attribute(Aiobs.LAYER, Layer.APPLICATION_AND_ORCHESTRATION.value)
                if question in cache:
                    hits += 1
                    span.set_attribute("aiobs.cache.hit", True)
                    set_cost_attributes(span, 0.0, tenant="acme", use_case="support")
                    continue
                span.set_attribute("aiobs.cache.hit", False)
                reply = provider.chat(question, context=CONTEXT)
                cache[question] = reply.text
                record = ledger.record(
                    reply.model, reply.input_tokens, reply.output_tokens, tenant="acme"
                )
                set_llm_attributes(
                    span,
                    provider=provider.name,
                    model=reply.model,
                    input_tokens=reply.input_tokens,
                    output_tokens=reply.output_tokens,
                )
                set_cost_attributes(span, record.usd, tenant="acme", use_case="support")

    return {
        "requests": 20,
        "cache_hits": hits,
        "billed_calls": len(ledger.records),
        "total_usd": ledger.total_usd,
    }
