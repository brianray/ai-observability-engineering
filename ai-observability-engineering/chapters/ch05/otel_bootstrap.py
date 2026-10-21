"""OpenTelemetry SDK bootstrap for a LangChain RAG pipeline.

Companion file: chapters/ch05/otel_bootstrap.py -- https://github.com/brianray/ai-observability-engineering/blob/main/ai-observability-engineering/chapters/ch05/otel_bootstrap.py
"""
import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)

SEMCONV_VERSION = "1.37.0"   # pin the convention version you built against


def configure_tracing(service_name: str = "rag-api") -> trace.Tracer:
    env = os.getenv("DEPLOY_ENV", "local")

    # The resource travels with every span; it is how a backend groups
    # spans by service, version, and environment.
    resource = Resource.create({
        "service.name": service_name,
        "service.version": os.getenv("SERVICE_VERSION", "dev"),
        "deployment.environment.name": env,
    })
    provider = TracerProvider(resource=resource)

    # Point at a collector, not directly at Jaeger or Tempo. The collector
    # is where routing, batching, and redaction live, so the app never
    # needs to know which backend is on the other end.
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    exporter = OTLPSpanExporter(
        endpoint=endpoint,
        insecure=endpoint.startswith("http://"),
    )

    if env == "local":
        # Simple processor: export each span the moment it ends, so it is
        # visible in Jaeger immediately. Never do this in production.
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    else:
        # Batch processor: queue spans and export in bulk on a schedule.
        # Costs a few seconds of visibility delay; saves a great deal of
        # exporter overhead under load.
        provider.add_span_processor(BatchSpanProcessor(
            exporter,
            max_queue_size=4096,
            schedule_delay_millis=2000,
            max_export_batch_size=512,
        ))

    trace.set_tracer_provider(provider)
    return trace.get_tracer("aiobs.ch05", SEMCONV_VERSION)
