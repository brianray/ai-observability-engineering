"""Telemetry bootstrap.

Every example in the book runs against the same tracer setup. In tests and
in the simulator, spans are captured in memory so they can be asserted on.
In a real deployment you swap the exporter and change nothing else.

    from aiobs.telemetry import configure, get_tracer

    configure(service_name="my-service", exporter="otlp")
    tracer = get_tracer(__name__)
"""

from __future__ import annotations

import os
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, cast

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import (
    ConsoleSpanExporter,
    SimpleSpanProcessor,
    SpanExporter,
)
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from .semconv import SEMCONV_VERSION

_MEMORY_EXPORTER: InMemorySpanExporter | None = None
_CONFIGURED = False


@dataclass(frozen=True)
class TelemetryConfig:
    service_name: str = "aiobs-example"
    service_version: str = "0.1.0"
    exporter: str = "memory"  # memory | console | otlp | none
    endpoint: str | None = None
    resource_attributes: dict[str, Any] = field(default_factory=dict)


def _build_exporter(config: TelemetryConfig) -> SpanExporter | None:
    global _MEMORY_EXPORTER
    if config.exporter == "memory":
        _MEMORY_EXPORTER = InMemorySpanExporter()
        return _MEMORY_EXPORTER
    if config.exporter == "console":
        return ConsoleSpanExporter()
    if config.exporter == "otlp":
        # Imported lazily: the OTLP exporter is an optional extra so that the
        # book's examples run with no network stack installed.
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # type: ignore
            OTLPSpanExporter,
        )

        endpoint = config.endpoint or os.environ.get(
            "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318/v1/traces"
        )
        return OTLPSpanExporter(endpoint=endpoint)
    if config.exporter == "none":
        return None
    raise ValueError(f"unknown exporter: {config.exporter!r}")


def configure(
    service_name: str = "aiobs-example",
    exporter: str = "memory",
    endpoint: str | None = None,
    force: bool = False,
    **resource_attributes: Any,
) -> TracerProvider:
    """Install a tracer provider. Idempotent unless ``force=True``."""
    global _CONFIGURED, _MEMORY_EXPORTER

    config = TelemetryConfig(
        service_name=service_name,
        exporter=exporter,
        endpoint=endpoint,
        resource_attributes=dict(resource_attributes),
    )

    if _CONFIGURED and not force:
        return cast(TracerProvider, trace.get_tracer_provider())

    resource = Resource.create(
        {
            "service.name": config.service_name,
            "service.version": config.service_version,
            "aiobs.semconv_version": SEMCONV_VERSION,
            **config.resource_attributes,
        }
    )
    provider = TracerProvider(resource=resource)
    span_exporter = _build_exporter(config)
    if span_exporter is not None:
        provider.add_span_processor(SimpleSpanProcessor(span_exporter))

    # OTel refuses to replace an installed global provider, so on ``force``
    # we reach past the guard deliberately. This is a test affordance, not
    # something to copy into production code.
    if force:
        trace._TRACER_PROVIDER = None
        trace._TRACER_PROVIDER_SET_ONCE._done = False

    trace.set_tracer_provider(provider)
    _CONFIGURED = True
    return provider


def get_tracer(name: str = "aiobs") -> trace.Tracer:
    if not _CONFIGURED:
        configure()
    return trace.get_tracer(name)


def get_finished_spans() -> Sequence[ReadableSpan]:
    """Spans captured so far. Only meaningful with the memory exporter."""
    if _MEMORY_EXPORTER is None:
        return ()
    return _MEMORY_EXPORTER.get_finished_spans()


def reset() -> None:
    """Drop captured spans. Called between tests and between examples."""
    if _MEMORY_EXPORTER is not None:
        _MEMORY_EXPORTER.clear()


@contextmanager
def capture(service_name: str = "aiobs-capture") -> Iterator[list[ReadableSpan]]:
    """Capture every span emitted inside the block.

        with capture() as spans:
            run_example()
        assert len(spans) == 3

    The returned list is populated on exit, not during the block.
    """
    configure(service_name=service_name, exporter="memory", force=True)
    reset()
    captured: list[ReadableSpan] = []
    try:
        yield captured
    finally:
        captured.extend(get_finished_spans())
