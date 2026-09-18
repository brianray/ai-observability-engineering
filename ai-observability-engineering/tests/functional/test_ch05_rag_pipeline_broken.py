from __future__ import annotations

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import aiobs.telemetry as telemetry
from chapters.ch05.rag_pipeline_broken import rag_pipeline_broken


def test_ch05_rag_pipeline_broken_orphans_rerank_span():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace._TRACER_PROVIDER = None
    trace._TRACER_PROVIDER_SET_ONCE._done = False
    trace.set_tracer_provider(provider)
    telemetry._CONFIGURED = True

    payload = rag_pipeline_broken()
    spans = exporter.get_finished_spans()
    spans_by_name = {span.name: span for span in spans}

    assert payload["reranked_docs"]

    request = spans_by_name["rag.request"]
    rerank = spans_by_name["rag.rerank"]

    assert rerank.context.trace_id != request.context.trace_id
    assert rerank.parent is None
