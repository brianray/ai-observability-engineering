"""Instrumentation helpers.

The book's central claim is that AI-native observability has to be designed
into the span schema rather than bolted on. These helpers are the practical
form of that claim: one decorator and one context manager that make it
harder to emit a span missing the attributes that matter.
"""

from __future__ import annotations

import functools
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, TypeVar

from opentelemetry import trace
from opentelemetry.trace import Span, SpanKind, Status, StatusCode

from .pillars import Layer, Pillar
from .semconv import Aiobs, Eval, GenAI, Operation
from .telemetry import get_tracer

F = TypeVar("F", bound=Callable[..., Any])


def set_llm_attributes(
    span: Span,
    *,
    provider: str,
    model: str,
    operation: str = Operation.CHAT,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    temperature: float | None = None,
    finish_reason: str | None = None,
    response_id: str | None = None,
) -> None:
    """Set the standardized ``gen_ai.*`` attributes on ``span``."""
    span.set_attribute(GenAI.PROVIDER_NAME, provider)
    span.set_attribute(GenAI.OPERATION_NAME, operation)
    span.set_attribute(GenAI.REQUEST_MODEL, model)
    if input_tokens is not None:
        span.set_attribute(GenAI.USAGE_INPUT_TOKENS, int(input_tokens))
    if output_tokens is not None:
        span.set_attribute(GenAI.USAGE_OUTPUT_TOKENS, int(output_tokens))
    if temperature is not None:
        span.set_attribute(GenAI.REQUEST_TEMPERATURE, float(temperature))
    if finish_reason is not None:
        span.set_attribute(GenAI.RESPONSE_FINISH_REASONS, [finish_reason])
    if response_id is not None:
        span.set_attribute(GenAI.RESPONSE_ID, response_id)


def set_eval_attributes(span: Span, scores: dict[str, float], evaluator: str | None = None) -> None:
    """Attach output-quality scores. CUSTOM namespace, not standardized."""
    mapping = {
        "hallucination": Eval.HALLUCINATION_SCORE,
        "groundedness": Eval.GROUNDEDNESS_SCORE,
        "relevance": Eval.RELEVANCE_SCORE,
        "toxicity": Eval.TOXICITY_SCORE,
    }
    for key, value in scores.items():
        attribute = mapping.get(key, f"eval.{key}_score")
        span.set_attribute(attribute, float(value))
    if evaluator:
        span.set_attribute(Eval.EVALUATOR, evaluator)


def set_cost_attributes(
    span: Span,
    usd: float,
    *,
    tenant: str = "unattributed",
    use_case: str = "unattributed",
) -> None:
    """Attach cost attribution. CUSTOM namespace (Chapters 7-9).

    ``tenant`` and ``use_case`` are always written, defaulting to
    ``"unattributed"`` rather than being omitted. Omitting them makes
    unattributed spend invisible; recording it as unattributed makes it
    countable, which is what Chapter 9 needs in order to report it.
    """
    span.set_attribute(Aiobs.COST_USD, round(float(usd), 6))
    span.set_attribute(Aiobs.COST_CURRENCY, "USD")
    span.set_attribute(Aiobs.COST_TENANT, tenant)
    span.set_attribute(Aiobs.COST_USE_CASE, use_case)


@contextmanager
def llm_span(
    name: str | None = None,
    *,
    provider: str,
    model: str,
    operation: str = Operation.CHAT,
    pillar: Pillar | None = None,
    layer: Layer | None = Layer.MODEL_AND_INFERENCE,
    tracer_name: str = "aiobs",
    **attributes: Any,
) -> Iterator[Span]:
    """Open a span already carrying the required GenAI attributes.

        with llm_span(provider="anthropic", model="claude-sonnet-4-5") as span:
            reply = client.chat(prompt)
            span.set_attribute(GenAI.USAGE_OUTPUT_TOKENS, reply.output_tokens)
    """
    span_name = name or f"{operation} {model}"
    tracer = get_tracer(tracer_name)
    with tracer.start_as_current_span(span_name, kind=SpanKind.CLIENT) as span:
        set_llm_attributes(span, provider=provider, model=model, operation=operation)
        if pillar is not None:
            span.set_attribute(Aiobs.PILLAR, pillar.value)
        if layer is not None:
            span.set_attribute(Aiobs.LAYER, layer.value)
        for key, value in attributes.items():
            if value is not None:
                span.set_attribute(key, value)
        try:
            yield span
        except Exception as exc:
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            raise


def observe(
    *,
    pillar: Pillar,
    layer: Layer,
    name: str | None = None,
    tracer_name: str = "aiobs",
) -> Callable[[F], F]:
    """Wrap any function in a span tagged with its pillar and layer.

    Used for the non-LLM steps in a pipeline: retrieval, tool calls,
    business-outcome recording. The pillar and layer tags are what let the
    simulator report coverage across the framework.
    """

    def decorator(func: F) -> F:
        span_name = name or func.__name__

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            tracer = get_tracer(tracer_name)
            with tracer.start_as_current_span(span_name) as span:
                span.set_attribute(Aiobs.PILLAR, pillar.value)
                span.set_attribute(Aiobs.LAYER, layer.value)
                started = time.perf_counter()
                try:
                    result = func(*args, **kwargs)
                except Exception as exc:
                    span.set_status(Status(StatusCode.ERROR, str(exc)))
                    span.record_exception(exc)
                    raise
                span.set_attribute(
                    "aiobs.duration_ms", round((time.perf_counter() - started) * 1000, 3)
                )
                return result

        return wrapper  # type: ignore[return-value]

    return decorator


def current_span() -> Span:
    return trace.get_current_span()
