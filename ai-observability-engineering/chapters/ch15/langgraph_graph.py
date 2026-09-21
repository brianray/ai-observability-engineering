"""The same pipeline as a real langgraph StateGraph (Listing 15.1).

``agent_graph.py`` runs this shape over plain callables so the book's
telemetry claims are testable without the dependency tree. This module
builds it with an actual ``StateGraph``, because Chapter 17's governance
checkpoint needs a real ``interrupt()`` and a checkpointer, and a book
that describes those without running them will describe them wrongly.

``langgraph`` is an optional extra::

    pip install -e ".[agents]"

Verified against langgraph 1.2.12; see ``langgraph_compat.py`` for the
pinned surface and the test that fails when it moves.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypedDict

from aiobs import Aiobs, Layer, Operation, Pillar, get_tracer
from aiobs.semconv import GenAI

from .agent_graph import MAX_HOPS, search_and_read, summarize, write_briefing


class GraphState(TypedDict, total=False):
    topic: str
    research: str
    draft: str
    review_decision: str
    attempt: int
    hop: int
    published: bool
    halted_at: str | None
    reviewer: str | None
    responsibility_chain: tuple


def _research_node(state: GraphState) -> dict[str, Any]:
    tracer = get_tracer(__name__)
    with tracer.start_as_current_span("agent.research") as span:
        span.set_attribute(GenAI.OPERATION_NAME, Operation.INVOKE_AGENT)
        span.set_attribute(GenAI.AGENT_NAME, "researcher")
        span.set_attribute(GenAI.PROVIDER_NAME, "internal")
        span.set_attribute(Aiobs.PILLAR, Pillar.PERFORMANCE.value)
        span.set_attribute(Aiobs.LAYER, Layer.APPLICATION_AND_ORCHESTRATION.value)
        return {"research": summarize(search_and_read(state["topic"])), "hop": 0, "attempt": 0}


def _draft_node(state: GraphState) -> dict[str, Any]:
    tracer = get_tracer(__name__)
    attempt = state.get("attempt", 0) + 1
    with tracer.start_as_current_span("agent.draft") as span:
        span.set_attribute(GenAI.OPERATION_NAME, Operation.INVOKE_AGENT)
        span.set_attribute(GenAI.AGENT_NAME, "writer")
        span.set_attribute(GenAI.PROVIDER_NAME, "internal")
        span.set_attribute("aiobs.agent.hop", state.get("hop", 0) + 1)
        return {
            "draft": write_briefing(state["research"], attempt),
            "attempt": attempt,
            "hop": state.get("hop", 0) + 1,
        }


def _make_review_node(reviewer: Callable[[str, int], str]):
    def _review_node(state: GraphState) -> dict[str, Any]:
        tracer = get_tracer(__name__)
        with tracer.start_as_current_span("agent.review") as span:
            span.set_attribute(GenAI.OPERATION_NAME, Operation.INVOKE_AGENT)
            span.set_attribute(GenAI.AGENT_NAME, "reviewer")
            span.set_attribute(GenAI.PROVIDER_NAME, "internal")
            decision = reviewer(state["draft"], state.get("attempt", 1))
            span.set_attribute("aiobs.agent.review_decision", decision)
            return {"review_decision": decision, "hop": state.get("hop", 0) + 1}

    return _review_node


def _route_after_review(state: GraphState) -> str:
    """Approve, revise, or stop because the cap is reached."""
    if state.get("review_decision") == "approve":
        return "approved"
    if state.get("hop", 0) >= MAX_HOPS:
        return "capped"
    return "revise"


def build_graph(
    reviewer: Callable[[str, int], str],
    *,
    checkpointer: Any | None = None,
    publish_node: Callable[[GraphState], dict[str, Any]] | None = None,
):
    """Build and compile the briefing graph.

    ``publish_node`` is where Chapter 17 inserts its governance
    checkpoint. Keeping it a parameter rather than a fixed node is what
    lets Chapter 17 reuse this graph instead of forking it.
    """
    from langgraph.graph import END, StateGraph

    graph = StateGraph(GraphState)
    graph.add_node("research", _research_node)
    graph.add_node("draft", _draft_node)
    graph.add_node("review", _make_review_node(reviewer))

    graph.set_entry_point("research")
    graph.add_edge("research", "draft")
    graph.add_edge("draft", "review")

    if publish_node is not None:
        graph.add_node("publish", publish_node)
        graph.add_conditional_edges(
            "review",
            _route_after_review,
            {"approved": "publish", "revise": "draft", "capped": END},
        )
        graph.add_edge("publish", END)
    else:
        graph.add_conditional_edges(
            "review",
            _route_after_review,
            {"approved": END, "revise": "draft", "capped": END},
        )

    return graph.compile(checkpointer=checkpointer)
