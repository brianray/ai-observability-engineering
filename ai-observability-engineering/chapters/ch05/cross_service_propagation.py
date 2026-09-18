"""Listing 5.5: trace-context propagation across a client and FastAPI route."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from opentelemetry import propagate, trace
from opentelemetry.trace import SpanKind

from aiobs import Aiobs, Layer, Pillar, get_tracer

from chapters.registry import example


@example(
    chapter=5,
    key="cross_service_propagation",
    title="Propagate trace context across a service boundary",
    pillar=Pillar.PERFORMANCE,
    layer=Layer.DATA_AND_RETRIEVAL,
    listing="5.5",
)
def cross_service_propagation() -> dict:
    """Carry trace context over HTTP headers, even in a local test client.

    The span tree should cross the service boundary intact. `traceparent`
    is the mechanism, but the point of the listing is operational: if the
    downstream retrieval service cannot join the caller's trace, latency
    attribution fractures exactly where the handoff matters.
    """

    tracer = get_tracer(__name__)
    app = FastAPI()

    @app.get("/retrieve")
    def retrieve(request: Request) -> dict[str, list[str]]:
        extracted = propagate.extract(dict(request.headers))
        with tracer.start_as_current_span(
            "rag.retrieve",
            context=extracted,
            kind=SpanKind.SERVER,
        ) as span:
            span.set_attribute(Aiobs.PILLAR, Pillar.PERFORMANCE.value)
            span.set_attribute(Aiobs.LAYER, Layer.DATA_AND_RETRIEVAL.value)
            return {"documents": ["retrieved policy excerpt", "refund exclusion note"]}

    with TestClient(app) as client:
        with tracer.start_as_current_span("rag.retrieve.client", kind=SpanKind.CLIENT) as span:
            span.set_attribute(Aiobs.PILLAR, Pillar.PERFORMANCE.value)
            span.set_attribute(Aiobs.LAYER, Layer.DATA_AND_RETRIEVAL.value)
            headers: dict[str, str] = {}
            propagate.inject(headers)
            response = client.get("/retrieve", headers=headers)

    return {"headers": headers, "documents": response.json()["documents"]}
