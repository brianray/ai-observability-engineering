"""Unit tests: Chapter 15 multi-agent tracing companion."""

from __future__ import annotations

import importlib

import pytest

from aiobs import Aiobs, Operation, capture
from aiobs.semconv import GenAI
from chapters.ch15 import (
    MAX_HOPS,
    MAX_PREVIEW,
    build_health_map,
    has_langgraph,
    log_handoff,
    payload_hash,
    render_health_map_dot,
    render_health_map_html,
    run_pipeline,
)
from chapters.ch15.agent_graph import RunTrace
from chapters.ch15.langgraph_compat import (
    PINNED_IMPORTS,
    PINNED_STATEGRAPH_METHODS,
    VERIFIED_LANGGRAPH_VERSION,
)

requires_langgraph = pytest.mark.skipif(
    not has_langgraph(), reason="langgraph is an optional extra"
)


# --- trace shape ---


def test_a_run_produces_exactly_one_research_span():
    _, trace = run_pipeline(run_index=1)
    assert trace.span_names().count("agent.research") == 1


def test_a_run_produces_a_draft_review_pair_with_increasing_hops():
    _, trace = run_pipeline(run_index=1)
    names = trace.span_names()
    assert "agent.draft" in names and "agent.review" in names

    hops = [hop for name, hop in trace.spans if name in ("agent.draft", "agent.review")]
    assert hops == sorted(hops)
    assert len(set(hops)) == len(hops), "hop numbers must be distinct"


def test_a_rejected_run_routes_to_revise_then_drafts_again():
    """One in five runs. The revise event must precede the second draft."""
    _, trace = run_pipeline(run_index=5)

    decisions = [d for name, d in trace.events if name == "agent.route"]
    assert decisions[0] == "revise"
    assert trace.span_names().count("agent.draft") == 2
    assert trace.approved


def test_four_in_five_runs_need_no_revision():
    rejected = [
        i for i in range(1, 21) if run_pipeline(run_index=i)[1].span_names().count("agent.draft") > 1
    ]
    assert rejected == [5, 10, 15, 20]


def test_the_hop_cap_terminates_a_run_the_reviewer_never_approves():
    """An unbounded revise loop is an unbounded spend."""
    _, trace = run_pipeline(reviewer=lambda draft, attempt: "revise")

    assert trace.terminated_by_cap
    assert not trace.approved
    hops = [hop for _, hop in trace.spans]
    assert max(hops) <= MAX_HOPS


def test_every_agent_span_carries_the_genai_attributes():
    with capture() as spans:
        run_pipeline(run_index=1)

    agent_spans = [s for s in spans if s.name.startswith("agent.")]
    assert agent_spans
    for span in agent_spans:
        attrs = dict(span.attributes or {})
        assert attrs[GenAI.OPERATION_NAME] == Operation.INVOKE_AGENT
        assert attrs[GenAI.AGENT_NAME]
        assert attrs[GenAI.PROVIDER_NAME]


def test_the_whole_run_is_one_trace():
    with capture() as spans:
        run_pipeline(run_index=5)

    trace_ids = {s.get_span_context().trace_id for s in spans}
    assert len(trace_ids) == 1, "a handoff that starts a new trace is a lost handoff"


def test_root_span_records_handoff_depth():
    with capture() as spans:
        run_pipeline(run_index=5)
    root = next(s for s in spans if s.name.startswith("invoke_agent"))
    assert dict(root.attributes or {})[Aiobs.AGENT_HANDOFF_DEPTH] > 0


# --- handoff logging ---


def test_log_handoff_never_exceeds_max_preview():
    trace = RunTrace()
    payload = "x" * (MAX_PREVIEW * 10)
    record = log_handoff(trace, "a", "b", payload, hop=1)

    assert len(record.preview) <= MAX_PREVIEW


def test_log_handoff_always_emits_a_hash_of_the_full_payload():
    trace = RunTrace()
    payload = "y" * (MAX_PREVIEW * 10)
    record = log_handoff(trace, "a", "b", payload, hop=1)

    assert record.payload_hash == payload_hash(payload)
    # Two payloads identical in the truncated preview stay distinguishable.
    other = log_handoff(trace, "a", "b", payload + "tail", hop=2)
    assert other.preview == record.preview
    assert other.payload_hash != record.payload_hash


def test_every_handoff_in_a_real_run_carries_a_hash():
    _, trace = run_pipeline(run_index=5)
    assert trace.handoffs
    for handoff in trace.handoffs:
        assert len(handoff.preview) <= MAX_PREVIEW
        assert len(handoff.payload_hash) == 64


# --- health map ---


@pytest.fixture(scope="module")
def health():
    traces = [run_pipeline(run_index=i)[1] for i in range(1, 101)]
    return build_health_map(traces)


def test_health_map_charges_rejects_to_the_upstream_node(health):
    """One run in five is rejected, so research owns 20 downstream rejects."""
    assert health["runs_analyzed"] == 100
    assert health["nodes"]["agent.research"]["runs"] == 100
    assert health["nodes"]["agent.research"]["downstream_rejects"] == 20


def test_health_map_reports_the_review_to_draft_edge_share(health):
    edge = health["edges"]["reviewer->writer"]
    assert edge["count"] == 20
    # 20 revise handoffs out of 240 total (100 research->writer,
    # 120 writer->reviewer, 20 reviewer->writer).
    assert edge["share"] == pytest.approx(20 / 240, abs=1e-6)


def test_health_map_renderings_exist_and_mention_the_nodes(health):
    dot = render_health_map_dot(health)
    assert dot.startswith("digraph")
    assert "agent.research" in dot and "reviewer" in dot

    html = render_health_map_html(health)
    assert "<table" in html and "agent.research" in html
    assert "100 runs" in html


# --- pinned langgraph surface ---


@requires_langgraph
def test_pinned_langgraph_imports_still_resolve():
    """Fails the build the day Listing 15.1 goes stale."""
    for module_path, names in PINNED_IMPORTS.items():
        module = importlib.import_module(module_path)
        for name in names:
            assert hasattr(module, name), f"{module_path} no longer exports {name}"


@requires_langgraph
def test_pinned_stategraph_methods_still_exist():
    from langgraph.graph import StateGraph

    for method in PINNED_STATEGRAPH_METHODS:
        assert hasattr(StateGraph, method), f"StateGraph.{method} is gone"


@requires_langgraph
def test_the_installed_langgraph_is_the_verified_one():
    import importlib.metadata as metadata

    installed = metadata.version("langgraph")
    if installed != VERIFIED_LANGGRAPH_VERSION:
        pytest.skip(
            f"langgraph {installed} installed, listing verified against "
            f"{VERIFIED_LANGGRAPH_VERSION}; re-verify before print"
        )


@requires_langgraph
def test_the_real_graph_runs_and_revises_once():
    from chapters.ch15.langgraph_graph import build_graph

    graph = build_graph(lambda draft, attempt: "revise" if attempt == 1 else "approve")
    with capture() as spans:
        result = graph.invoke({"topic": "refund policy change"})

    assert result["review_decision"] == "approve"
    assert result["attempt"] == 2
    assert [s.name for s in spans].count("agent.draft") == 2


@requires_langgraph
def test_the_real_graph_respects_the_hop_cap():
    from chapters.ch15.langgraph_graph import build_graph

    graph = build_graph(lambda draft, attempt: "revise")
    result = graph.invoke({"topic": "x"})
    assert result["review_decision"] == "revise"
    assert result["hop"] >= MAX_HOPS
