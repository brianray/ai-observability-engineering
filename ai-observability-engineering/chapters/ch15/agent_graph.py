"""One trace across a multi-agent pipeline (Listing 15.1).

The pipeline is research -> draft -> review, with review able to send
work back to draft. That cycle is the part worth instrumenting: a
rejected draft produces a second ``agent.draft`` span in the *same*
trace, and the number of times that happens is the signal that tells you
the research step is feeding the writer bad material.

Written over plain callables rather than langgraph so the telemetry
claims are testable without the dependency. ``langgraph_graph.py``
builds the same shape with a real ``StateGraph`` for readers who want it;
Chapter 17's governance checkpoint uses that one, because it needs a real
``interrupt()``.

The hop cap is not decoration. A reviewer that never approves is a
perfectly ordinary failure, and without a cap it is an unbounded spend.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypedDict

from aiobs import Aiobs, Layer, Operation, Pillar, get_tracer
from aiobs.semconv import GenAI

#: Maximum draft/review round trips before the run is terminated.
MAX_HOPS = 6

#: Handoff payload previews are truncated to this many characters. The
#: full payload is identified by hash, never carried.
MAX_PREVIEW = 120


class BriefingState(TypedDict, total=False):
    """The state the graph carries. Mirrors the langgraph TypedDict pattern."""

    topic: str
    research: str
    draft: str
    review_decision: str
    hop: int
    history: list[str]


@dataclass
class HandoffRecord:
    source: str
    target: str
    preview: str
    payload_hash: str
    hop: int


@dataclass
class RunTrace:
    """What a single run emitted, for the health map."""

    spans: list[tuple[str, int]] = field(default_factory=list)
    events: list[tuple[str, str]] = field(default_factory=list)
    handoffs: list[HandoffRecord] = field(default_factory=list)
    approved: bool = False
    terminated_by_cap: bool = False

    def span_names(self) -> list[str]:
        return [name for name, _ in self.spans]


def payload_hash(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def log_handoff(trace: RunTrace, source: str, target: str, payload: str, hop: int) -> HandoffRecord:
    """Record a handoff without recording what was handed off.

    The preview is capped and the hash always accompanies it, so two
    handoffs that look identical in the preview are still
    distinguishable, and the full payload stays out of telemetry.
    """
    record = HandoffRecord(
        source=source,
        target=target,
        preview=payload[:MAX_PREVIEW],
        payload_hash=payload_hash(payload),
        hop=hop,
    )
    trace.handoffs.append(record)
    return record


# --- node implementations, stubbed over the mock provider ---


def search_and_read(topic: str) -> str:
    return f"findings on {topic}: three sources reviewed, two corroborate"


def summarize(research: str) -> str:
    return f"summary: {research[:60]}"


def write_briefing(summary: str, attempt: int) -> str:
    return f"briefing draft {attempt} based on {summary[:40]}"


def make_reviewer(run_index: int, *, reject_every: int = 5) -> Callable[[str, int], str]:
    """A reviewer that rejects the FIRST draft of every ``reject_every``-th run.

    Rejecting once, not forever: the point is one revise loop, so the run
    produces a second ``agent.draft`` span and then finishes. A reviewer
    that rejects every attempt exercises the hop cap instead, which is a
    different test (and one ``run_pipeline`` covers separately).

    Deterministic by run index rather than random, because a health map
    built from a seeded coin flip is not reproducible across machines.
    """

    def check_briefing(draft: str, attempt: int) -> str:
        if run_index % reject_every == 0 and attempt == 1:
            return "revise"
        return "approve"

    return check_briefing


def run_pipeline(
    topic: str = "refund policy change",
    *,
    run_index: int = 1,
    reviewer: Callable[[str, int], str] | None = None,
    max_hops: int = MAX_HOPS,
) -> tuple[BriefingState, RunTrace]:
    """Run research -> draft -> review, revising until approved or capped."""
    tracer = get_tracer(__name__)
    check_briefing = reviewer or make_reviewer(run_index)
    trace = RunTrace()
    state: BriefingState = {"topic": topic, "hop": 0, "history": []}

    with tracer.start_as_current_span("invoke_agent briefing_pipeline") as root:
        root.set_attribute(GenAI.OPERATION_NAME, Operation.INVOKE_AGENT)
        root.set_attribute(GenAI.AGENT_NAME, "briefing_pipeline")
        root.set_attribute(GenAI.PROVIDER_NAME, "internal")
        root.set_attribute(Aiobs.PILLAR, Pillar.PERFORMANCE.value)
        root.set_attribute(Aiobs.LAYER, Layer.APPLICATION_AND_ORCHESTRATION.value)

        # --- research, exactly once per run ---
        with tracer.start_as_current_span("agent.research") as span:
            span.set_attribute(GenAI.OPERATION_NAME, Operation.INVOKE_AGENT)
            span.set_attribute(GenAI.AGENT_NAME, "researcher")
            span.set_attribute(GenAI.PROVIDER_NAME, "internal")
            span.set_attribute("aiobs.agent.hop", 0)
            state["research"] = summarize(search_and_read(topic))
            trace.spans.append(("agent.research", 0))
        log_handoff(trace, "researcher", "writer", state["research"], hop=0)

        attempt = 0
        while state["hop"] < max_hops:
            attempt += 1
            hop = state["hop"] + 1
            state["hop"] = hop

            with tracer.start_as_current_span("agent.draft") as span:
                span.set_attribute(GenAI.OPERATION_NAME, Operation.INVOKE_AGENT)
                span.set_attribute(GenAI.AGENT_NAME, "writer")
                span.set_attribute(GenAI.PROVIDER_NAME, "internal")
                span.set_attribute("aiobs.agent.hop", hop)
                state["draft"] = write_briefing(state["research"], attempt)
                trace.spans.append(("agent.draft", hop))
            log_handoff(trace, "writer", "reviewer", state["draft"], hop=hop)

            hop += 1
            state["hop"] = hop
            with tracer.start_as_current_span("agent.review") as span:
                span.set_attribute(GenAI.OPERATION_NAME, Operation.INVOKE_AGENT)
                span.set_attribute(GenAI.AGENT_NAME, "reviewer")
                span.set_attribute(GenAI.PROVIDER_NAME, "internal")
                span.set_attribute("aiobs.agent.hop", hop)
                decision = check_briefing(state["draft"], attempt)
                state["review_decision"] = decision
                span.set_attribute("aiobs.agent.review_decision", decision)
                trace.spans.append(("agent.review", hop))

            # The routing decision is an event on the trace, so a revise
            # loop is visible without diffing span counts.
            root.add_event("agent.route", {"decision": decision, "hop": hop})
            trace.events.append(("agent.route", decision))

            if decision == "approve":
                trace.approved = True
                break
            log_handoff(trace, "reviewer", "writer", state["draft"], hop=hop)
        else:
            trace.terminated_by_cap = True

        root.set_attribute(Aiobs.AGENT_HANDOFF_DEPTH, len(trace.handoffs))
        root.set_attribute("aiobs.agent.approved", trace.approved)
        root.set_attribute("aiobs.agent.terminated_by_cap", trace.terminated_by_cap)

    return state, trace


# --- health map ---


def build_health_map(traces: list[RunTrace]) -> dict[str, Any]:
    """Aggregate many runs into a per-node and per-edge picture.

    ``downstream_rejects`` is the number the map exists for: it charges a
    rejection to the node whose output the rejected work was built from,
    not to the node that produced the rejected draft. A writer that keeps
    getting sent back is usually a research problem.
    """
    node_runs: Counter[str] = Counter()
    downstream_rejects: Counter[str] = Counter()
    edges: Counter[tuple[str, str]] = Counter()

    for trace in traces:
        for name, _ in trace.spans:
            node_runs[name] += 1
        rejects = sum(1 for _, decision in trace.events if decision == "revise")
        if rejects:
            # Research ran once and fed every draft in this run.
            downstream_rejects["agent.research"] += rejects
            downstream_rejects["agent.draft"] += rejects
        for handoff in trace.handoffs:
            edges[(handoff.source, handoff.target)] += 1

    total_edges = sum(edges.values())
    by_node = {
        name: {
            "runs": count,
            "downstream_rejects": downstream_rejects.get(name, 0),
        }
        for name, count in sorted(node_runs.items())
    }
    by_edge = {
        f"{source}->{target}": {
            "count": count,
            "share": round(count / total_edges, 6) if total_edges else 0.0,
        }
        for (source, target), count in sorted(edges.items())
    }

    return {
        "runs_analyzed": len(traces),
        "nodes": by_node,
        "edges": by_edge,
        "approved": sum(1 for t in traces if t.approved),
        "terminated_by_cap": sum(1 for t in traces if t.terminated_by_cap),
    }


def render_health_map_dot(health: dict[str, Any]) -> str:
    """Graphviz DOT rendering. Edge width tracks traffic share."""
    lines = [
        "digraph agent_health {",
        '  rankdir=LR;',
        '  node [shape=box, style=rounded, fontname="Helvetica"];',
    ]
    for name, stats in health["nodes"].items():
        rejects = stats["downstream_rejects"]
        colour = "red" if rejects else "black"
        label = f"{name}\\nruns={stats['runs']}\\ndownstream_rejects={rejects}"
        lines.append(f'  "{name}" [label="{label}", color={colour}];')
    for edge, stats in health["edges"].items():
        source, target = edge.split("->")
        width = max(1.0, round(stats["share"] * 6, 2))
        lines.append(
            f'  "{source}" -> "{target}" '
            f'[label="{stats["share"]:.0%}", penwidth={width}];'
        )
    lines.append("}")
    return "\n".join(lines)


def render_health_map_html(health: dict[str, Any]) -> str:
    """A small self-contained page, for readers without Graphviz installed."""
    rows = "".join(
        f"<tr><td>{name}</td><td>{s['runs']}</td><td>{s['downstream_rejects']}</td></tr>"
        for name, s in health["nodes"].items()
    )
    edge_rows = "".join(
        f"<tr><td>{edge}</td><td>{s['count']}</td><td>{s['share']:.1%}</td></tr>"
        for edge, s in health["edges"].items()
    )
    return (
        "<!doctype html><meta charset='utf-8'>"
        "<title>Agent health map</title>"
        "<style>body{font:14px system-ui;margin:2rem}"
        "table{border-collapse:collapse;margin-bottom:2rem}"
        "td,th{border:1px solid #ccc;padding:.4rem .8rem;text-align:left}</style>"
        f"<h1>Agent health map</h1><p>{health['runs_analyzed']} runs, "
        f"{health['approved']} approved, {health['terminated_by_cap']} hit the hop cap.</p>"
        "<h2>Nodes</h2><table><tr><th>Node</th><th>Runs</th>"
        f"<th>Downstream rejects</th></tr>{rows}</table>"
        "<h2>Edges</h2><table><tr><th>Edge</th><th>Count</th>"
        f"<th>Share</th></tr>{edge_rows}</table>"
    )
