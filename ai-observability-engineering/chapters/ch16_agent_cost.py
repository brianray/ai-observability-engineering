"""Chapter 16: Cost and Failure Control in Agentic Systems."""

from __future__ import annotations

from aiobs import AgentRun, Aiobs, Layer, Pillar, get_tracer
from aiobs.agents import classify, failure_vector
from aiobs.cost import price_call
from aiobs.testing.scenarios import get as get_scenario

from .registry import example

TOKEN_BUDGET = 20_000


@example(
    chapter=16,
    key="silent_retry_loop_detected",
    title="Catching the $47,000 retry loop from Chapter 1",
    pillar=Pillar.ROI,
    layer=Layer.APPLICATION_AND_ORCHESTRATION,
    listing="16.1",
    demonstrates_failure=True,
)
def silent_retry_loop_detected() -> dict:
    """The failure that opens the book, now with a detector on it.

    Nothing here looks at status codes, because the failure never
    produced one.
    """
    tracer = get_tracer(__name__)
    run: AgentRun = get_scenario("silent_retry_loop")()  # type: ignore[assignment]

    with tracer.start_as_current_span("agent_budget_guard") as span:
        span.set_attribute(Aiobs.PILLAR, Pillar.ROI.value)
        span.set_attribute(Aiobs.LAYER, Layer.APPLICATION_AND_ORCHESTRATION.value)
        modes = classify(run, token_budget=TOKEN_BUDGET)
        span.set_attribute(Aiobs.MAST_FAILURE_MODE, [m.value for m in modes])
        span.set_attribute("aiobs.agent.total_tokens", run.total_tokens)
        span.set_attribute("aiobs.agent.token_budget", TOKEN_BUDGET)
        wasted = price_call("mock-sonnet-1", run.total_tokens, 0)
        span.set_attribute(Aiobs.COST_USD, round(wasted, 6))
        span.set_attribute(Aiobs.COST_CURRENCY, "USD")
        span.set_attribute(Aiobs.COST_TENANT, "acme")

    return {
        "steps": len(run.steps),
        "total_tokens": run.total_tokens,
        "over_budget": run.total_tokens > TOKEN_BUDGET,
        "mast_failure_modes": [m.value for m in modes],
        "wasted_usd": round(wasted, 6),
        "http_errors": 0,
        "uptime_pct": 99.99,
    }


@example(
    chapter=16,
    key="failure_vector_across_runs",
    title="A failure histogram instead of a pass/fail rate",
    pillar=Pillar.PERFORMANCE,
    layer=Layer.APPLICATION_AND_ORCHESTRATION,
    listing="16.5",
)
def failure_vector_across_runs() -> dict:
    """MAST's contribution in one line: replace "41% failed" with which
    fourteen ways they failed, because only the second one tells you what
    to fix."""
    tracer = get_tracer(__name__)
    runs = [
        get_scenario("silent_retry_loop")(),
        get_scenario("no_termination")(),
        get_scenario("unverified_output")(),
    ]
    with tracer.start_as_current_span("failure_analysis") as span:
        span.set_attribute(Aiobs.PILLAR, Pillar.PERFORMANCE.value)
        span.set_attribute(Aiobs.LAYER, Layer.APPLICATION_AND_ORCHESTRATION.value)
        vector = failure_vector(runs)  # type: ignore[arg-type]
        span.set_attribute("aiobs.agent.failure_modes", sorted(vector))
        span.set_attribute("aiobs.agent.runs_analyzed", len(runs))
    return {"runs": len(runs), "failure_vector": vector}
