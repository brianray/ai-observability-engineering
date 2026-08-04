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
