from __future__ import annotations

import aiobs.telemetry as telemetry
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from chapters.ch05.cross_service_propagation import cross_service_propagation


def test_ch05_cross_service_propagation_keeps_parent_child_relationship():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace._TRACER_PROVIDER = None
    trace._TRACER_PROVIDER_SET_ONCE._done = False
    trace.set_tracer_provider(provider)
    telemetry._CONFIGURED = True

    payload = cross_service_propagation()
    spans = exporter.get_finished_spans()
    spans_by_name = {span.name: span for span in spans}

    assert "traceparent" in payload["headers"]

    client = spans_by_name["rag.retrieve.client"]
    server = spans_by_name["rag.retrieve"]

    assert server.parent is not None
    assert server.parent.span_id == client.context.span_id
