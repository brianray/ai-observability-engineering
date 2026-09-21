"""Unit tests: Chapter 17 accountability companion."""

from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest

from aiobs import Aiobs, capture, get_tracer
from chapters.ch12 import AuditLogger, LocalFilesystemStore, verify_chain
from chapters.ch15 import has_langgraph
from chapters.ch17_accountability import (
    DECISION_APPROVE,
    DECISION_REJECT,
    ApprovalResponse,
    ChainNotStartedError,
    Hop,
    annotate_current_span,
    apply_context,
    assemble_decision_record,
    carry_context,
    chain_as_json,
    current_chain,
    current_principal,
    delegate,
    make_governance_checkpoint,
    release_context,
    start_chain,
)

requires_langgraph = pytest.mark.skipif(
    not has_langgraph(), reason="langgraph is an optional extra"
)


@pytest.fixture()
def audit(tmp_path):
    return AuditLogger(LocalFilesystemStore(tmp_path / "audit"))


# --- the chain ---


def test_delegate_outside_start_chain_raises():
    with pytest.raises(ChainNotStartedError):
        delegate("orphan_agent")


def test_a_handoff_with_no_delegated_by_inherits_the_previous_principal():
    with start_chain("intake_agent", "human_operator"):
        hop = delegate("planner_agent")
        assert hop.principal == "human_operator"

        explicit = delegate("executor_agent", delegated_by="planner_agent")
        assert explicit.principal == "planner_agent"
        assert current_principal() == "planner_agent"


def test_the_chain_grows_by_one_entry_per_delegate():
    with start_chain("intake_agent", "human_operator"):
        assert len(current_chain()) == 1
        delegate("planner_agent")
        assert len(current_chain()) == 2
        delegate("executor_agent")
        assert len(current_chain()) == 3


def test_the_chain_attribute_is_valid_json_on_the_current_span():
    with capture() as spans:
        tracer = get_tracer(__name__)
        with start_chain("intake_agent", "human_operator"):
            with tracer.start_as_current_span("act"):
                delegate("planner_agent")
                annotate_current_span()

    attrs = dict(spans[0].attributes or {})
    payload = json.loads(attrs[Aiobs.RESPONSIBILITY_CHAIN])
    assert [h["actor"] for h in payload] == ["intake_agent", "planner_agent"]
    assert attrs[Aiobs.RESPONSIBILITY_PRINCIPAL] == "human_operator"


def test_the_chain_is_restored_when_the_scope_exits():
    with start_chain("a", "op"):
        delegate("b")
    assert current_chain() == ()


def test_two_concurrent_runs_produce_independent_chains():
    """A ContextVar is task-local. Two runs must not interleave."""

    async def run(name: str, principal: str, hops: int) -> str:
        with start_chain(f"{name}_intake", principal):
            for i in range(hops):
                await asyncio.sleep(0)  # force interleaving
                delegate(f"{name}_agent_{i}")
            await asyncio.sleep(0)
            return chain_as_json()

    async def main():
        return await asyncio.gather(
            run("alpha", "operator_a", 3), run("beta", "operator_b", 3)
        )

    alpha, beta = asyncio.run(main())
    alpha_hops, beta_hops = json.loads(alpha), json.loads(beta)

    assert [h["actor"] for h in alpha_hops] == [
        "alpha_intake", "alpha_agent_0", "alpha_agent_1", "alpha_agent_2",
    ]
    assert [h["actor"] for h in beta_hops] == [
        "beta_intake", "beta_agent_0", "beta_agent_1", "beta_agent_2",
    ]
    assert {h["principal"] for h in alpha_hops} == {"operator_a"}
    assert {h["principal"] for h in beta_hops} == {"operator_b"}


def test_the_chain_is_empty_on_a_pool_thread_without_the_attach_pattern():
    """The negative case. This is why the ContextVar must be carried."""

    async def main():
        loop = asyncio.get_running_loop()
        with start_chain("intake_agent", "human_operator"):
            delegate("planner_agent")
            with ThreadPoolExecutor(max_workers=1) as pool:
                return await loop.run_in_executor(pool, current_chain)

    assert asyncio.run(main()) == (), (
        "run_in_executor starts the callable in a fresh context; if this ever "
        "returns a populated chain, the negative example in Section 17.3 is wrong"
    )


def test_the_chain_survives_the_pool_boundary_with_the_attach_pattern():
    """Chapter 5's Listing 5.4 attach/detach, applied to the chain."""

    def work(snapshot):
        token = apply_context(snapshot)
        try:
            return current_chain()
        finally:
            release_context(token)

    async def main():
        loop = asyncio.get_running_loop()
        with start_chain("intake_agent", "human_operator"):
            delegate("planner_agent")
            snapshot = carry_context()
            with ThreadPoolExecutor(max_workers=1) as pool:
                return await loop.run_in_executor(pool, work, snapshot)

    carried = asyncio.run(main())
    assert [h.actor for h in carried] == ["intake_agent", "planner_agent"]
    assert carried[-1].principal == "human_operator"


# --- governance checkpoint, without a langgraph runtime ---


def _node(audit, response, **kw):
    return make_governance_checkpoint(audit, interrupt_fn=lambda _: response, **kw)


def test_approval_records_a_checkpoint_span_with_the_reviewer(audit):
    node = _node(audit, ApprovalResponse(DECISION_APPROVE, "dana", "editor_in_chief"))
    with capture() as spans:
        with start_chain("intake_agent", "human_operator"):
            result = node({"draft": "briefing text"})

    span = next(s for s in spans if s.name == "checkpoint.publish")
    attrs = dict(span.attributes or {})
    assert attrs["aiobs.checkpoint.reviewer"] == "dana"
    assert attrs[Aiobs.HUMAN_REVIEW_OUTCOME] == DECISION_APPROVE
    assert result["published"] is True


def test_approval_writes_an_oversight_action_to_the_audit_log(audit):
    node = _node(audit, ApprovalResponse(DECISION_APPROVE, "dana", "editor_in_chief"))
    with start_chain("intake_agent", "human_operator"):
        node({"draft": "briefing text"})

    records = audit.records()
    assert len(records) == 1
    assert records[0].payload["event_type"] == "oversight_action"
    assert records[0].payload["reviewer"] == "dana"
    assert verify_chain(records).verified


def test_after_approval_the_last_hop_names_the_reviewer_as_principal(audit):
    node = _node(audit, ApprovalResponse(DECISION_APPROVE, "dana", "editor_in_chief"))
    with start_chain("intake_agent", "human_operator"):
        delegate("writer_agent")
        node({"draft": "briefing text"})
        chain = current_chain()

    assert chain[-1].principal == "dana"
    assert chain[-1].actor == "publish_checkpoint"


def test_a_resume_with_the_wrong_role_raises_permission_error(audit):
    node = _node(audit, ApprovalResponse(DECISION_APPROVE, "sam", "intern"))
    with start_chain("intake_agent", "human_operator"):
        with pytest.raises(PermissionError):
            node({"draft": "briefing text"})

    # A rejected credential must not leave an approval trail.
    assert audit.records() == []


def test_a_reject_halts_the_run_with_halted_at_set(audit):
    node = _node(audit, ApprovalResponse(DECISION_REJECT, "dana", "compliance_officer", "off policy"))
    with start_chain("intake_agent", "human_operator"):
        result = node({"draft": "briefing text"})

    assert result["published"] is False
    assert result["halted_at"] == "publish"
    assert audit.records()[0].payload["decision"] == DECISION_REJECT


# --- governance checkpoint, end to end on a real graph ---


@requires_langgraph
def test_real_graph_runs_to_the_interrupt_and_resumes_with_an_approval(audit):
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.types import Command

    from chapters.ch15.langgraph_graph import build_graph

    node = make_governance_checkpoint(audit)
    graph = build_graph(
        lambda draft, attempt: "approve",
        checkpointer=InMemorySaver(),
        publish_node=node,
    )
    config = {"configurable": {"thread_id": "t-1"}}

    with capture() as spans:
        with start_chain("intake_agent", "human_operator"):
            paused = graph.invoke({"topic": "refund policy change"}, config)
            assert "__interrupt__" in paused, "the graph must stop at the checkpoint"
            assert paused["__interrupt__"][0].value["checkpoint"] == "publish"

            resumed = graph.invoke(
                Command(
                    resume={
                        "decision": DECISION_APPROVE,
                        "reviewer": "dana",
                        "reviewer_role": "editor_in_chief",
                        "note": "",
                    }
                ),
                config,
            )
            # Read the chain from the state, not the ContextVar: a node
            # boundary discards the ContextVar mutation.
            chain = resumed["responsibility_chain"]

    assert resumed["published"] is True
    assert any(s.name == "checkpoint.publish" for s in spans)
    assert audit.records()[0].payload["event_type"] == "oversight_action"
    assert chain[-1].principal == "dana"


@requires_langgraph
def test_the_contextvar_chain_does_not_escape_a_graph_node(audit):
    """The boundary that forces the chain into the graph state.

    A langgraph node runs in its own copied context, so delegate()
    inside a node is invisible to the caller afterwards. Same shape as
    the thread-pool negative case, same fix: carry it explicitly.
    """
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.types import Command

    from chapters.ch15.langgraph_graph import build_graph

    graph = build_graph(
        lambda draft, attempt: "approve",
        checkpointer=InMemorySaver(),
        publish_node=make_governance_checkpoint(audit),
    )
    config = {"configurable": {"thread_id": "t-4"}}

    with start_chain("intake_agent", "human_operator"):
        graph.invoke({"topic": "x"}, config)
        result = graph.invoke(
            Command(
                resume={
                    "decision": DECISION_APPROVE,
                    "reviewer": "dana",
                    "reviewer_role": "editor_in_chief",
                    "note": "",
                }
            ),
            config,
        )
        outside = current_chain()

    assert outside[-1].principal == "human_operator", (
        "if this ever sees 'dana', the node boundary stopped discarding the "
        "ContextVar and Section 17.3's guidance needs revisiting"
    )
    assert result["responsibility_chain"][-1].principal == "dana"


@requires_langgraph
def test_real_graph_reject_halts_the_run(audit):
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.types import Command

    from chapters.ch15.langgraph_graph import build_graph

    graph = build_graph(
        lambda draft, attempt: "approve",
        checkpointer=InMemorySaver(),
        publish_node=make_governance_checkpoint(audit),
    )
    config = {"configurable": {"thread_id": "t-2"}}

    with start_chain("intake_agent", "human_operator"):
        graph.invoke({"topic": "x"}, config)
        result = graph.invoke(
            Command(
                resume={
                    "decision": DECISION_REJECT,
                    "reviewer": "dana",
                    "reviewer_role": "compliance_officer",
                    "note": "off policy",
                }
            ),
            config,
        )

    assert result["published"] is False
    assert result["halted_at"] == "publish"


@requires_langgraph
def test_real_graph_rejects_a_resume_from_the_wrong_role(audit):
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.types import Command

    from chapters.ch15.langgraph_graph import build_graph

    graph = build_graph(
        lambda draft, attempt: "approve",
        checkpointer=InMemorySaver(),
        publish_node=make_governance_checkpoint(audit),
    )
    config = {"configurable": {"thread_id": "t-3"}}

    with start_chain("intake_agent", "human_operator"):
        graph.invoke({"topic": "x"}, config)
        with pytest.raises(PermissionError):
            graph.invoke(
                Command(resume={"decision": "approve", "reviewer": "sam", "reviewer_role": "intern"}),
                config,
            )


# --- decision record ---


def _record(**overrides):
    base = {
        "decision_id": "dec-1",
        "trace_id": "0" * 32,
        "occurred_at": datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc),
        "system_id": "credit-prescreen",
        "action": "publish_briefing",
        "outcome": "published",
        "chain": (
            Hop("intake_agent", "human_operator", "start"),
            Hop("publish_checkpoint", "dana", "approve"),
        ),
        "model": "mock-sonnet-1",
        "policy_version": "refund-policy-2026-03",
        "audit_record_hash": "a" * 64,
        "inputs_ref": "vault://briefings/1",
        "risk_category": "high",
        "frameworks": ("eu_ai_act", "nist_ai_rmf"),
        "reviewer": "dana",
        "review_decision": "approve",
    }
    base.update(overrides)
    return assemble_decision_record(**base)


def test_every_table_17_3_field_is_populated_for_the_case_study_run():
    record = _record()
    assert record.complete, record.missing_fields
    assert record.missing_fields == ()
    payload = record.to_dict()
    for key in (
        "decision_id", "trace_id", "occurred_at", "system_id", "action", "outcome",
        "accountable_principal", "responsibility_chain", "model", "policy_version",
        "reviewer", "review_decision", "audit_record_hash", "inputs_ref",
        "risk_category", "frameworks",
    ):
        assert key in payload, f"Table 17.3 field {key} missing from the record"


def test_the_accountable_principal_is_the_last_hops_principal_not_its_actor():
    record = _record()
    assert record.accountable_principal == "dana"
    assert record.responsibility_chain[-1].actor == "publish_checkpoint"


def test_missing_fields_are_named_rather_than_left_silent():
    record = _record(policy_version="")
    assert not record.complete
    assert "policy_version" in record.missing_fields


def test_an_unreviewed_decision_is_still_complete():
    """Review fields are optional; the rest are not."""
    record = _record(reviewer=None, review_decision=None)
    assert record.complete


def test_a_record_with_no_chain_is_refused():
    with pytest.raises(ValueError):
        _record(chain=())
