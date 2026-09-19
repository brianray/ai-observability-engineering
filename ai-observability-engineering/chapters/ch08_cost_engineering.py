"""Chapter 8: Engineering Cost Down."""

from __future__ import annotations


import json

from aiobs import Aiobs, CostLedger, Layer, MockProvider, Pillar, get_tracer, GenAI

from aiobs.instrument import set_cost_attributes, set_llm_attributes

from .ch08.model_router import LARGE_MODEL, PRICING_PATH, cost_estimate_usd
from .registry import example

CONTEXT = "Standard shipping takes three to five business days"


def table_8_1_rates() -> dict[str, dict[str, float]]:
    """Model rates (USD per million tokens) sourced from chapters/ch08/pricing.json."""
    pricing = json.loads(PRICING_PATH.read_text(encoding="utf-8"))
    return pricing["models"]


def chapter_opening_cost_figure_usd() -> float:
    """Opening figure for 1,500 input and 400 output tokens on the large model."""
    return cost_estimate_usd(LARGE_MODEL, 1500, 400)


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


@example(
    chapter=8,
    key="retry_attempt_accounting",
    title="A silent retry still doubles billable work",
    pillar=Pillar.ROI,
    layer=Layer.APPLICATION_AND_ORCHESTRATION,
)
def retry_attempt_accounting() -> dict:
    """Retries are cost events even when the user only sees one answer."""
    tracer = get_tracer(__name__)
    prompt = "What is the shipping policy?"
    providers = {
        "no_retry": MockProvider(retry_fraction=0.0),
        "one_retry": MockProvider(retry_fraction=1.0),
    }
    ledger = CostLedger()

    def _record(label: str, provider: MockProvider) -> dict:
        with tracer.start_as_current_span(label) as span:
            span.set_attribute(Aiobs.LAYER, Layer.APPLICATION_AND_ORCHESTRATION.value)
            reply = provider.chat(prompt, context=CONTEXT)
            record = ledger.record(reply.model, reply.input_tokens, reply.output_tokens, tenant="acme")
            set_llm_attributes(
                span,
                provider=provider.name,
                model=reply.model,
                input_tokens=reply.input_tokens,
                output_tokens=reply.output_tokens,
                finish_reason=reply.finish_reason,
                response_id=reply.response_id,
            )
            set_cost_attributes(span, record.usd, tenant="acme", use_case="support")
            span.set_attribute(Aiobs.REQUEST_ATTEMPTS, reply.attempts)
            for index, attempt_model in enumerate(reply.attempt_models, start=1):
                with tracer.start_as_current_span(f"{label}.attempt_{index}") as attempt:
                    attempt.set_attribute(GenAI.REQUEST_MODEL, attempt_model)
            return {
                "attempts": reply.attempts,
                "attempt_models": list(reply.attempt_models),
                "input_tokens": reply.input_tokens,
                "output_tokens": reply.output_tokens,
                "cost_usd": record.usd,
            }

    with tracer.start_as_current_span("retry_accounting") as root:
        root.set_attribute(Aiobs.PILLAR, Pillar.ROI.value)
        root.set_attribute(Aiobs.LAYER, Layer.APPLICATION_AND_ORCHESTRATION.value)
        without_retry = _record("no_retry", providers["no_retry"])
        with_retry = _record("one_retry", providers["one_retry"])

    return {
        "without_retry": without_retry,
        "with_retry": with_retry,
        "retry_overhead_usd": round(
            with_retry["cost_usd"] - without_retry["cost_usd"],
            6,
        ),
    }
