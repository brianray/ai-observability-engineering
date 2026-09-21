"""Chapter 4: Instrumenting LLM and Agent Pipelines with OpenTelemetry."""

from __future__ import annotations

from aiobs import Aiobs, Layer, MockProvider, Operation, Pillar, get_tracer, llm_span, observe
from aiobs.evals import default_suite
from aiobs.instrument import set_eval_attributes, set_llm_attributes
from aiobs.semconv import GenAI

from .registry import example

DOCS = {
    "warranty": "Hardware carries a twelve month limited warranty from delivery",
    "refunds": "Refund extensions apply only to active products purchased after March 2025",
}
SLO_TARGETS = {
    "latency_p95_ms": {
        "target": 400.0,
        "goal": "at_most",
        "source": "Chapter 4 scorecard latency SLO",
    },
    "ttft_ms": {
        "target": 60.0,
        "goal": "at_most",
        "source": "Chapter 4 scorecard TTFT SLO",
    },
    "tokens_per_second": {
        "target": 45.0,
        "goal": "at_least",
        "source": "Chapter 4 scorecard throughput floor",
    },
    "groundedness": {
        "target": 0.85,
        "goal": "at_least",
        "source": "Chapter 4 scorecard groundedness floor",
    },
    "hallucination": {
        "target": 0.1,
        "goal": "at_most",
        "source": "Chapter 4 scorecard hallucination ceiling",
    },
}
_SCORECARD_FACTORS = {
    "current": {
        "ttft_ms": 1.0,
        "tokens_per_second": 1.0,
        "groundedness": 1.0,
        "hallucination": 1.0,
    },
    "prior": {
        "ttft_ms": 1.1,
        "tokens_per_second": 0.99,
        "groundedness": 0.99,
        "hallucination": 1.1,
    },
}


class _DeterministicClock:
    def __init__(self) -> None:
        self._now = 0.0

    def now(self) -> float:
        return self._now

    def sleep(self, seconds: float) -> None:
        self._now += seconds


def slo_targets_from_ch04() -> dict[str, dict[str, object]]:
    """Return the Chapter 4 scorecard definitions used by Chapter 9."""
    return {metric: dict(spec) for metric, spec in SLO_TARGETS.items()}


def chapter_4_scorecard(
    provider: MockProvider | None = None, *, period: str = "current"
) -> dict[str, float]:
    """Deterministic Chapter 4 scorecard figures for executive reporting."""
    try:
        factors = _SCORECARD_FACTORS[period]
    except KeyError as exc:
        raise ValueError(f"unknown period {period!r}") from exc

    active_provider = provider or MockProvider()
    question = "what are the warranty terms"
    context = ". ".join(_search(question))
    reply = active_provider.chat(question, context=context)
    scores = default_suite().scores(reply.text, context=context, prompt=question)
    latency = measure_ttft(clock=_DeterministicClock(), provider=active_provider)
    return {
        "ttft_ms": round(latency["ttft_ms"] * factors["ttft_ms"], 3),
        "tokens_per_second": round(
            latency["tokens_per_second"] * factors["tokens_per_second"], 3
        ),
        "groundedness": round(scores["groundedness"] * factors["groundedness"], 6),
        "hallucination": round(scores["hallucination"] * factors["hallucination"], 6),
    }


@observe(pillar=Pillar.PERFORMANCE, layer=Layer.DATA_AND_RETRIEVAL, name="vector_search")
def _search(query: str, k: int = 2) -> list[str]:
    ranked = sorted(DOCS.items(), key=lambda kv: -len(set(kv[1].lower().split()) & set(query.lower().split())))
    return [text for _, text in ranked[:k]]


@example(
    chapter=4,
    key="rag_pipeline_traced",
    title="A RAG pipeline traced end to end",
    pillar=Pillar.PERFORMANCE,
    layer=Layer.DATA_AND_RETRIEVAL,
    listing="4.3",
)
def rag_pipeline_traced() -> dict:
    """Retrieval, generation, and evaluation as one trace with three spans.

    The nesting matters. A flat list of spans tells you what happened; a
    tree tells you what caused what, which is the difference between a
    log aggregator and a trace.
    """
    tracer = get_tracer(__name__)
    provider = MockProvider()
    question = "what are the warranty terms"

    with tracer.start_as_current_span("rag.answer") as root:
        root.set_attribute(Aiobs.LAYER, Layer.APPLICATION_AND_ORCHESTRATION.value)
        root.set_attribute(Aiobs.PILLAR, Pillar.PERFORMANCE.value)

        documents = _search(question)
        context = ". ".join(documents)
        reply = provider.chat(question, context=context)

        with llm_span(
            provider=provider.name,
            model=provider.model,
            operation=Operation.CHAT,
            pillar=Pillar.PERFORMANCE,
        ) as span:
            set_llm_attributes(
                span,
                provider=provider.name,
                model=reply.model,
                input_tokens=reply.input_tokens,
                output_tokens=reply.output_tokens,
                finish_reason=reply.finish_reason,
            )
            scores = default_suite().scores(reply.text, context=context, prompt=question)
            set_eval_attributes(span, scores, evaluator="heuristic-v1")

    return {"documents_retrieved": len(documents), "answer": reply.text, "scores": scores}


@example(
    chapter=4,
    key="measure_ttft",
    title="Measuring time to first token",
    pillar=Pillar.PERFORMANCE,
    layer=Layer.MODEL_AND_INFERENCE,
    listing="4.5",
)
def measure_ttft(clock=None, provider: MockProvider | None = None) -> dict:
    """TTFT starts with the first non-empty content delta, not the role chunk."""
    provider = provider or MockProvider()
    prompt = "what are the warranty terms"
    context = DOCS["warranty"]
    active_clock = clock or _DeterministicClock()
    started = active_clock.now()
    first_token_at: float | None = None
    finished_at = started
    response_id = ""
    finish_reason = "stop"
    usage = None
    tokens: list[str] = []

    with llm_span(
        provider=provider.name,
        model=provider.model,
        operation=Operation.CHAT,
        pillar=Pillar.PERFORMANCE,
        layer=Layer.MODEL_AND_INFERENCE,
    ) as span:
        stream = provider.stream_chat(
            prompt,
            context=context,
            stream_options={"include_usage": True},
            clock=active_clock,
        )
        for chunk in stream:
            finished_at = active_clock.now()
            response_id = chunk.id
            if not chunk.choices:
                usage = chunk.usage
                continue
            choice = chunk.choices[0]
            finish_reason = choice.finish_reason or finish_reason
            content = choice.delta.content or ""
            if not content:
                continue
            if first_token_at is None:
                first_token_at = finished_at
            tokens.append(content)

        output_tokens = usage.completion_tokens if usage is not None else len(tokens)
        input_tokens = usage.prompt_tokens if usage is not None else provider.count_tokens(prompt + context)
        ttft_ms = round((first_token_at - started) * 1000, 3) if first_token_at is not None else 0.0
        total_ms = round((finished_at - started) * 1000, 3)
        generation_window = max(finished_at - (first_token_at or finished_at), 1e-6)
        tokens_per_second = round(output_tokens / generation_window, 3)
        span.set_attribute("aiobs.latency.ttft_ms", ttft_ms)
        span.set_attribute("aiobs.latency.total_ms", total_ms)
        span.set_attribute("aiobs.throughput.tokens_per_second", tokens_per_second)
        set_llm_attributes(
            span,
            provider=provider.name,
            model=provider.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            finish_reason=finish_reason,
            response_id=response_id,
        )

    return {
        "answer": "".join(tokens),
        "ttft_ms": ttft_ms,
        "total_ms": total_ms,
        "tokens_per_second": tokens_per_second,
        "output_tokens": output_tokens,
    }


@example(
    chapter=4,
    key="tool_call_span",
    title="Instrumenting a tool call",
    pillar=Pillar.PERFORMANCE,
    layer=Layer.APPLICATION_AND_ORCHESTRATION,
    listing="4.6",
)
def tool_call_span() -> dict:
    tracer = get_tracer(__name__)
    with tracer.start_as_current_span("execute_tool lookup_order") as span:
        span.set_attribute(GenAI.OPERATION_NAME, Operation.EXECUTE_TOOL)
        span.set_attribute(GenAI.TOOL_NAME, "lookup_order")
        span.set_attribute(GenAI.PROVIDER_NAME, "internal")
        # No model, no tokens. A tool span is a GenAI span that did not
        # call a model, and inventing model="n/a" to satisfy a linter
        # makes the trace worse, not better.
        span.set_attribute(Aiobs.LAYER, Layer.APPLICATION_AND_ORCHESTRATION.value)
        span.set_attribute(Aiobs.PILLAR, Pillar.PERFORMANCE.value)
        result = {"order_id": "A-2291", "status": "shipped"}
        span.set_attribute("aiobs.tool.result_keys", sorted(result))
    return {"tool": "lookup_order", "result": result}
