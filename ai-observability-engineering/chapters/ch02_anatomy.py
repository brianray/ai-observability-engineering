"""Chapter 2: Anatomy of an Observable AI System.

The five observable layers, instrumented as one trace. The point the
chapter keeps returning to is visible in the output: OpenTelemetry covers
the middle three layers well and thins out at both edges, so the
infrastructure and outcome layers need instrumentation you write yourself.
"""

from __future__ import annotations

from aiobs import Aiobs, Layer, MockProvider, Pillar, get_tracer, llm_span, observe
from aiobs.cost import price_call
from aiobs.instrument import set_cost_attributes, set_llm_attributes
from aiobs.pillars import ALL_LAYERS

from .registry import example

CORPUS = {
    "refunds": "Refund extensions apply only to active products purchased after March 2025",
    "warranty": "Hardware carries a twelve month limited warranty from delivery",
}


@observe(pillar=Pillar.PERFORMANCE, layer=Layer.INFRASTRUCTURE, name="gpu.allocate")
def _allocate_capacity(replicas: int) -> dict:
    return {"replicas": replicas, "queue_depth": 3}


@observe(pillar=Pillar.PERFORMANCE, layer=Layer.DATA_AND_RETRIEVAL, name="retrieve")
def _retrieve(query: str) -> str:
    hits = [text for key, text in CORPUS.items() if key in query.lower()]
    return ". ".join(hits) or "no documents matched"


@observe(pillar=Pillar.ROI, layer=Layer.BUSINESS_AND_OUTCOMES, name="record_outcome")
def _record_outcome(resolved: bool, cost_usd: float) -> dict:
    return {"resolved": resolved, "cost_per_resolution": cost_usd if resolved else None}


@example(
    chapter=2,
    key="five_layers_one_trace",
    title="One request across all five observable layers",
    pillar=Pillar.PERFORMANCE,
    layer=Layer.APPLICATION_AND_ORCHESTRATION,
    listing="2.4",
)
def five_layers_one_trace() -> dict:
    tracer = get_tracer(__name__)
    provider = MockProvider()
    question = "what are the refunds rules"

    with tracer.start_as_current_span("handle_request") as root:
        root.set_attribute(Aiobs.LAYER, Layer.APPLICATION_AND_ORCHESTRATION.value)
        root.set_attribute(Aiobs.PILLAR, Pillar.PERFORMANCE.value)

        _allocate_capacity(2)
        context = _retrieve(question)
        reply = provider.chat(question, context=context)

        with llm_span(
            provider=provider.name,
            model=provider.model,
            pillar=Pillar.PERFORMANCE,
            layer=Layer.MODEL_AND_INFERENCE,
        ) as span:
            set_llm_attributes(
                span,
                provider=provider.name,
                model=reply.model,
                input_tokens=reply.input_tokens,
                output_tokens=reply.output_tokens,
            )
            cost = price_call(reply.model, reply.input_tokens, reply.output_tokens)
            set_cost_attributes(span, cost, tenant="acme", use_case="support")

        _record_outcome(resolved=True, cost_usd=cost)

    return {
        "layers": [layer.value for layer in ALL_LAYERS],
        "otel_coverage": {layer.value: layer.otel_coverage for layer in ALL_LAYERS},
        "cost_usd": cost,
        "answer": reply.text,
    }


@example(
    chapter=2,
    key="collector_pipeline_sampling",
    title="Why a sampled pipeline cannot be a cost system of record",
    pillar=Pillar.ROI,
    layer=Layer.BUSINESS_AND_OUTCOMES,
    listing="2.7",
)
def collector_pipeline_sampling() -> dict:
    """Head sampling at 10% loses 90% of spend, not 90% of precision.

    Latency percentiles survive sampling. Totals do not. This is the
    architectural reason the outcome layer needs its own unsampled path.
    """
    from aiobs.cost import CostLedger

    provider = MockProvider()
    full = CostLedger()
    sampled = CostLedger()

    with get_tracer(__name__).start_as_current_span("batch") as span:
        span.set_attribute(Aiobs.LAYER, Layer.BUSINESS_AND_OUTCOMES.value)
        span.set_attribute(Aiobs.PILLAR, Pillar.ROI.value)
        for i in range(100):
            # Real traffic is not uniform. Request sizes vary, which is
            # exactly why extrapolating a total from a sample fails: the
            # sample happens to catch cheap requests or expensive ones.
            prompt = "explain the policy " * (1 + (i * 7) % 9)
            reply = provider.chat(prompt, context=CORPUS["refunds"])
            full.record(reply.model, reply.input_tokens, reply.output_tokens, tenant="acme")
            if i % 10 == 0:
                sampled.record(
                    reply.model, reply.input_tokens, reply.output_tokens, tenant="acme"
                )
        error = abs(sampled.total_usd * 10 - full.total_usd) / full.total_usd
        span.set_attribute("aiobs.cost.sampling_error", round(error, 6))

    return {
        "true_total_usd": full.total_usd,
        "extrapolated_from_sample_usd": round(sampled.total_usd * 10, 6),
        "relative_error": round(error, 6),
        "conclusion": "sample for traces, never for the cost ledger",
    }
