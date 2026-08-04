"""Chapter 1: The Observability Imperative for AI Systems.

Listing 1.1 is the chapter's central argument in code: the same request
instrumented twice, once the way a classical APM tool sees it and once
the way it has to be seen to be meaningfully observable.
"""

from __future__ import annotations

from aiobs import (
    Aiobs,
    Eval,
    GenAI,
    Layer,
    MockProvider,
    Operation,
    Pillar,
    default_suite,
    get_tracer,
    llm_span,
    set_eval_attributes,
    set_llm_attributes,
)
from aiobs.providers import FailureMode

from .registry import example

CONTEXT = (
    "Refund extensions apply only to active products purchased after "
    "March 2025. Discontinued products are not eligible."
)
QUESTION = "Is the discontinued model still eligible for a refund extension?"


@example(
    chapter=1,
    key="traditional_vs_llm_span",
    title="The same request, instrumented twice",
    pillar=Pillar.PERFORMANCE,
    layer=Layer.MODEL_AND_INFERENCE,
    listing="1.1",
)
def traditional_vs_llm_span() -> dict:
    tracer = get_tracer(__name__)

    # Block one: what a classical APM tool records. Two attributes, and
    # by both of them this request is healthy.
    with tracer.start_as_current_span("GET /api/answer") as span:
        span.set_attribute("http.response.status_code", 200)
        span.set_attribute("http.server.request.duration", 0.142)
        span.set_attribute(Aiobs.LAYER, Layer.APPLICATION_AND_ORCHESTRATION.value)

    # Block two: what has to be added for the same request to be
    # observable as an LLM call. The gen_ai.* names are standardized; the
    # eval.* names are this book's, and are not.
    provider = MockProvider()
    reply = provider.chat(QUESTION, context=CONTEXT)
    scores = default_suite().scores(reply.text, context=CONTEXT, prompt=QUESTION)

    with llm_span(
        provider=provider.name,
        model=provider.model,
        operation=Operation.CHAT,
        pillar=Pillar.PERFORMANCE,
        layer=Layer.MODEL_AND_INFERENCE,
    ) as span:
        set_llm_attributes(
            span,
            provider=provider.name,
            model=reply.model,
            input_tokens=reply.input_tokens,
            output_tokens=reply.output_tokens,
            finish_reason=reply.finish_reason,
            response_id=reply.response_id,
        )
        set_eval_attributes(span, scores, evaluator="heuristic-v1")
        span.set_attribute(Eval.EVAL_SET_VERSION, "v1")

    return {
        "answer": reply.text,
        "tokens": reply.total_tokens,
        "scores": scores,
        "attributes_added": [
            GenAI.PROVIDER_NAME,
            GenAI.OPERATION_NAME,
            GenAI.REQUEST_MODEL,
            GenAI.USAGE_INPUT_TOKENS,
            GenAI.USAGE_OUTPUT_TOKENS,
            Eval.HALLUCINATION_SCORE,
            Eval.GROUNDEDNESS_SCORE,
        ],
    }


@example(
    chapter=1,
    key="green_dashboard_wrong_answer",
    title="Every metric healthy, the answer wrong",
    pillar=Pillar.RESPONSIBILITY,
    layer=Layer.MODEL_AND_INFERENCE,
    demonstrates_failure=True,
    tags=("exercise-1.1",),
)
def green_dashboard_wrong_answer() -> dict:
    """Exercise 1.1 in executable form.

    Latency, error rate, and uptime are all fine. The only signal that
    catches this is the one no APM tool emits.
    """
    provider = MockProvider(failure_mode=FailureMode.CONFIDENTLY_WRONG)
    reply = provider.chat(QUESTION, context=CONTEXT)
    scores = default_suite().scores(reply.text, context=CONTEXT, prompt=QUESTION)

    with llm_span(
        provider=provider.name,
        model=provider.model,
        pillar=Pillar.RESPONSIBILITY,
        layer=Layer.MODEL_AND_INFERENCE,
    ) as span:
        set_llm_attributes(
            span,
            provider=provider.name,
            model=reply.model,
            input_tokens=reply.input_tokens,
            output_tokens=reply.output_tokens,
        )
        # A traditional dashboard would show exactly these two, both green.
        span.set_attribute("http.response.status_code", 200)
        span.set_attribute("http.server.request.duration", 0.138)
        set_eval_attributes(span, scores, evaluator="heuristic-v1")

    caught_by_pillar = "responsibility" if scores["groundedness"] < 0.6 else None
    return {
        "answer": reply.text,
        "status_code": 200,
        "latency_s": 0.138,
        "scores": scores,
        "caught_by_pillar": caught_by_pillar,
        "would_apm_catch_it": False,
    }
