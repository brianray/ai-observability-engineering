"""Chapter 3: Signals, Scopes, and the Telemetry Contract.

Four signal types (logs, metrics, traces, evals) and the four-level scope
hierarchy (span, trace, session, experiment). The example builds one
session out of several traces and shows what each scope can and cannot
answer.
"""

from __future__ import annotations

from aiobs import (
    Aiobs,
    Layer,
    MockProvider,
    Pillar,
    Scope,
    default_suite,
    get_logger,
    get_tracer,
)
from aiobs.instrument import set_eval_attributes, set_llm_attributes
from aiobs.semconv import GenAI

from .registry import example

#: The one structured logger. Chapter 10's detector imports the same
#: factory, so a reader who wires up this chapter's logging gets
#: Chapter 10's security events on the same stream, already
#: correlated to the trace.
log = get_logger(__name__)

CONTEXT = "Standard shipping takes three to five business days"
_PROMETHEUS_WINDOWS = {
    "current": {"request_count": 2400, "error_rate": 0.004, "latency_p50_ms": 182.0, "latency_p95_ms": 460.0},
    "prior": {"request_count": 2360, "error_rate": 0.005, "latency_p50_ms": 179.0, "latency_p95_ms": 380.0},
}


def prometheus_signal_snapshot(
    provider: MockProvider | None = None, *, period: str = "current"
) -> dict[str, float]:
    """Deterministic Prometheus-style counters and latency rollups.

    Chapter 9 needs period-over-period comparisons that can run in CI
    without a live collector. The seeded mock provider supplies stable
    token counts; the fixed window values stand in for the counters and
    histogram summaries a Prometheus scrape would expose.
    """
    try:
        window = _PROMETHEUS_WINDOWS[period]
    except KeyError as exc:
        raise ValueError(f"unknown period {period!r}") from exc

    active_provider = provider or MockProvider()
    reply = active_provider.chat("how long is shipping", context=CONTEXT)
    requests = window["request_count"]
    return {
        "request_count": float(requests),
        "error_rate": window["error_rate"],
        "latency_p50_ms": window["latency_p50_ms"],
        "latency_p95_ms": window["latency_p95_ms"],
        "input_tokens_total": float(reply.input_tokens * requests),
        "output_tokens_total": float(reply.output_tokens * requests),
    }


@example(
    chapter=3,
    key="scope_hierarchy",
    title="Span, trace, session, experiment",
    pillar=Pillar.PERFORMANCE,
    layer=Layer.APPLICATION_AND_ORCHESTRATION,
    listing="3.2",
)
def scope_hierarchy() -> dict:
    tracer = get_tracer(__name__)
    provider = MockProvider()
    suite = default_suite()
    session_id = "session-4417"
    experiment_id = "exp-prompt-v3"

    turn_scores = []
    for turn, question in enumerate(
        ["how long is shipping", "is expedited shipping available"], start=1
    ):
        with tracer.start_as_current_span(f"turn_{turn}") as trace_root:
            trace_root.set_attribute(GenAI.CONVERSATION_ID, session_id)
            trace_root.set_attribute("aiobs.experiment_id", experiment_id)
            trace_root.set_attribute(Aiobs.LAYER, Layer.APPLICATION_AND_ORCHESTRATION.value)
            trace_root.set_attribute(Aiobs.PILLAR, Pillar.PERFORMANCE.value)

            reply = provider.chat(question, context=CONTEXT)
            with tracer.start_as_current_span("chat") as span:
                set_llm_attributes(
                    span,
                    provider=provider.name,
                    model=reply.model,
                    input_tokens=reply.input_tokens,
                    output_tokens=reply.output_tokens,
                )
                scores = suite.scores(reply.text, context=CONTEXT, prompt=question)
                set_eval_attributes(span, scores, evaluator="heuristic-v1")
                turn_scores.append(scores)

    return {
        "scopes": {
            Scope.SPAN.value: "one step: this model call",
            Scope.TRACE.value: "one user turn, end to end",
            Scope.SESSION.value: f"every turn in {session_id}",
            Scope.EXPERIMENT.value: f"every session under {experiment_id}",
        },
        "session_id": session_id,
        "turns": len(turn_scores),
        "mean_groundedness": round(
            sum(s["groundedness"] for s in turn_scores) / len(turn_scores), 6
        ),
    }


@example(
    chapter=3,
    key="four_signals",
    title="What each signal type answers, and what it cannot",
    pillar=Pillar.PERFORMANCE,
    layer=Layer.MODEL_AND_INFERENCE,
    listing="3.5",
)
def four_signals() -> dict:
    tracer = get_tracer(__name__)
    provider = MockProvider()
    question = "how long is shipping"
    reply = provider.chat(question, context=CONTEXT)
    scores = default_suite().scores(reply.text, context=CONTEXT, prompt=question)

    with tracer.start_as_current_span("chat") as span:
        set_llm_attributes(
            span,
            provider=provider.name,
            model=reply.model,
            input_tokens=reply.input_tokens,
            output_tokens=reply.output_tokens,
        )
        set_eval_attributes(span, scores, evaluator="heuristic-v1")
        # The log signal, emitted through the shared structured logger
        # rather than as a span event. A span event is part of the trace;
        # a log is its own signal, and the chapter's point is that they
        # answer different questions.
        log.emit("retrieval.completed", documents=1, source="policy_kb")

    return {
        "logs": "discrete events: retrieval.completed fired once",
        "metrics": {"tokens": reply.total_tokens},
        "traces": "causal structure: which step caused which",
        "evals": scores,
        "signal_that_catches_a_wrong_answer": "evals",
    }
