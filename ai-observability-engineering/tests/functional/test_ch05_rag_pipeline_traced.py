from __future__ import annotations

import aiobs.telemetry as telemetry
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind

from chapters.ch05.rag_pipeline_traced import rag_pipeline_traced


def test_ch05_rag_pipeline_traced_parents_every_span():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    from opentelemetry import trace

    trace._TRACER_PROVIDER = None
    trace._TRACER_PROVIDER_SET_ONCE._done = False
    trace.set_tracer_provider(provider)
    telemetry._CONFIGURED = True

    payload = rag_pipeline_traced()
    spans = exporter.get_finished_spans()
    spans_by_name = {span.name: span for span in spans}

    assert payload["retrieved_docs"]
    assert len({span.context.trace_id for span in spans}) == 1

    request = spans_by_name["rag.request"]
    retrieve = spans_by_name["rag.retrieve"]
    rerank = spans_by_name["rag.rerank"]
    generate = spans_by_name["rag.generate"]
    post_process = spans_by_name["rag.post_process"]

    assert request.kind is SpanKind.SERVER
    assert retrieve.parent is not None
    assert retrieve.parent.span_id == request.context.span_id
    assert generate.parent is not None
    assert generate.parent.span_id == request.context.span_id
    assert post_process.parent is not None
    assert post_process.parent.span_id == request.context.span_id
    assert rerank.parent is not None
    assert rerank.parent.span_id == retrieve.context.span_id
