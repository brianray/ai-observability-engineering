"""Chapter 5: Performance Metrics That Matter."""

from __future__ import annotations

import os
import time

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
)
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from aiobs import Aiobs, Layer, MockProvider, Pillar, get_tracer
import aiobs.telemetry as telemetry
from aiobs.instrument import set_llm_attributes

from .registry import example

CONTEXT = "Expedited shipping is next business day for orders placed before 2pm"


@example(
    chapter=5,
    key="deployment_environment_resource",
    title="Pin the deployment environment in the resource",
    pillar=Pillar.PERFORMANCE,
    layer=Layer.MODEL_AND_INFERENCE,
    listing="5.1",
)
def deployment_environment_resource() -> dict:
    """Set the deployment environment in the Resource, not on every span.

    OTel's semantic convention key is ``deployment.environment.name``; the older
    ``deployment.environment`` name was renamed in the spec. In CI we run the
    example locally with ``DEPLOY_ENV=local`` and an in-memory exporter so we
    assert the resource model without requiring a live collector.
    """
    env = os.environ.get("DEPLOY_ENV", "local")
    resource = Resource.create({"deployment.environment.name": env})
    exporter = InMemorySpanExporter()
    telemetry._MEMORY_EXPORTER = exporter
    provider = TracerProvider(resource=resource)

    if env == "local":
        processor = BatchSpanProcessor(
            exporter,
            schedule_delay_millis=5000,
            max_export_batch_size=512,
        )
    else:
        processor = SimpleSpanProcessor(exporter)
    provider.add_span_processor(processor)

    tracer = provider.get_tracer(__name__)
    with tracer.start_as_current_span("deployment_environment_fingerprint") as span:
        span.set_attribute(Aiobs.PILLAR, Pillar.PERFORMANCE.value)
        span.set_attribute(Aiobs.LAYER, Layer.MODEL_AND_INFERENCE.value)

    provider.force_flush()
    spans = exporter.get_finished_spans()
    resource_attributes = dict(resource.attributes)
    return {
        "deployment_environment": env,
        "resource_attribute_count": len(resource_attributes),
        "resource_attributes": resource_attributes,
        "processor": type(processor).__name__,
        "batch_config": (
            {"schedule_delay_millis": 5000, "max_export_batch_size": 512}
            if isinstance(processor, BatchSpanProcessor)
            else None
        ),
        "span_count": len(spans),
    }


def _percentile(values: list[float], p: float) -> float:
    if not values:
        raise ValueError("no observations")
    ordered = sorted(values)
    k = (len(ordered) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    return round(ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo), 6)


@example(
    chapter=5,
    key="latency_distribution",
    title="Percentiles, not averages",
    pillar=Pillar.PERFORMANCE,
    layer=Layer.MODEL_AND_INFERENCE,
    listing="5.2",
)
def latency_distribution() -> dict:
    """A mean latency of 200ms is compatible with a p99 of four seconds.

    Report percentiles. The average is the number that hides the users
    who are actually having a bad time.
    """
    tracer = get_tracer(__name__)
    provider = MockProvider()
    latencies: list[float] = []

    with tracer.start_as_current_span("load_test") as span:
        span.set_attribute(Aiobs.PILLAR, Pillar.PERFORMANCE.value)
        span.set_attribute(Aiobs.LAYER, Layer.MODEL_AND_INFERENCE.value)
        for i in range(50):
            started = time.perf_counter()
            reply = provider.chat(f"question {i}", context=CONTEXT)
            elapsed_ms = (time.perf_counter() - started) * 1000
            # Deterministic synthetic tail so the example is reproducible.
            latencies.append(elapsed_ms + (900.0 if i % 25 == 0 else 40.0))
        span.set_attribute("aiobs.latency.p50_ms", _percentile(latencies, 0.50))
        span.set_attribute("aiobs.latency.p95_ms", _percentile(latencies, 0.95))
        span.set_attribute("aiobs.latency.p99_ms", _percentile(latencies, 0.99))
        set_llm_attributes(
            span,
            provider=provider.name,
            model=provider.model,
            input_tokens=reply.input_tokens,
            output_tokens=reply.output_tokens,
        )

    mean = round(sum(latencies) / len(latencies), 6)
    return {
        "mean_ms": mean,
        "p50_ms": _percentile(latencies, 0.50),
        "p95_ms": _percentile(latencies, 0.95),
        "p99_ms": _percentile(latencies, 0.99),
        "tail_hidden_by_mean": _percentile(latencies, 0.99) > mean * 2,
    }


@example(
    chapter=5,
    key="tokens_per_second",
    title="Throughput measured in tokens, not requests",
    pillar=Pillar.PERFORMANCE,
    layer=Layer.MODEL_AND_INFERENCE,
    listing="5.6",
)
def tokens_per_second() -> dict:
    tracer = get_tracer(__name__)
    provider = MockProvider()
    total_tokens = 0
    started = time.perf_counter()

    with tracer.start_as_current_span("throughput") as span:
        span.set_attribute(Aiobs.PILLAR, Pillar.PERFORMANCE.value)
        span.set_attribute(Aiobs.LAYER, Layer.MODEL_AND_INFERENCE.value)
        for i in range(25):
            reply = provider.chat(f"batch item {i}", context=CONTEXT)
            total_tokens += reply.total_tokens
        elapsed = max(time.perf_counter() - started, 1e-6)
        span.set_attribute("aiobs.throughput.tokens_per_second", round(total_tokens / elapsed, 3))
        set_llm_attributes(
            span,
            provider=provider.name,
            model=provider.model,
            input_tokens=reply.input_tokens,
            output_tokens=reply.output_tokens,
        )

    return {
        "requests": 25,
        "total_tokens": total_tokens,
        "note": "capacity scales with tokens; request rate alone will mislead you",
    }
    
