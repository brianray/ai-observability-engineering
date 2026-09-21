"""Chapter 17: Accountability When Responsibility Is Delegated.

This is the module path the manuscript cites, and it is the single import
surface for all three of the chapter's listings:

* Listing 17.1, the responsibility chain: ``start_chain``, ``delegate``,
  ``current_chain``, ``annotate_current_span``
* Listing 17.2, the governance checkpoint: ``make_governance_checkpoint``,
  ``ApprovalRequest``, ``ApprovalResponse``
* Listing 17.3, the decision record: ``DecisionRecord``,
  ``assemble_decision_record``

The implementations live in ``chapters/ch17/`` as three separate modules,
following the same pattern as Chapters 5, 6 and 8, because three distinct
concerns in one file is how the second one stops being readable. They are
re-exported here so the manuscript's citation resolves and a reader can
import everything from one place::

    from chapters.ch17_accountability import start_chain, delegate
"""

from __future__ import annotations

from aiobs import AgentRun, Aiobs, Layer, MockProvider, Pillar, get_tracer
from aiobs.instrument import set_llm_attributes
from aiobs.semconv import GenAI

from .ch17 import (
    DECISION_APPROVE,
    DECISION_REJECT,
    DEFAULT_APPROVER_ROLES,
    ApprovalRequest,
    ApprovalResponse,
    ChainNotStartedError,
    DecisionRecord,
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
from .registry import example

__all__ = [
    "DECISION_APPROVE",
    "DECISION_REJECT",
    "DEFAULT_APPROVER_ROLES",
    "ApprovalRequest",
    "ApprovalResponse",
    "ChainNotStartedError",
    "DecisionRecord",
    "Hop",
    "accountability_chain",
    "annotate_current_span",
    "apply_context",
    "assemble_decision_record",
    "carry_context",
    "chain_as_json",
    "current_chain",
    "current_principal",
    "delegate",
    "make_governance_checkpoint",
    "release_context",
    "start_chain",
]

CONTEXT = "Configuration changes to production require a named approver"
CHAIN = [
    ("intake_agent", "human_operator"),
    ("planner_agent", "intake_agent"),
    ("executor_agent", "planner_agent"),
]


@example(
    chapter=17,
    key="accountability_chain",
    title="Who authorized this, three agents deep",
    pillar=Pillar.RESPONSIBILITY,
    layer=Layer.APPLICATION_AND_ORCHESTRATION,
    listing="17.2",
)
def accountability_chain() -> dict:
    """When agent C acts, someone has to be able to answer "on whose
    authority." Carrying the authorizing principal across handoffs is
    what makes that answerable after the fact rather than a reconstruction
    exercise during an incident."""
    tracer = get_tracer(__name__)
    provider = MockProvider()
    run = AgentRun(task="apply the configuration change")

    with tracer.start_as_current_span("delegation_chain") as root:
        root.set_attribute(Aiobs.PILLAR, Pillar.RESPONSIBILITY.value)
        root.set_attribute(Aiobs.LAYER, Layer.APPLICATION_AND_ORCHESTRATION.value)
        root.set_attribute("aiobs.accountability.originating_principal", "human_operator")

        for agent, authorized_by in CHAIN:
            with tracer.start_as_current_span(f"invoke_agent {agent}") as span:
                span.set_attribute(GenAI.AGENT_NAME, agent)
                span.set_attribute("aiobs.accountability.authorized_by", authorized_by)
                span.set_attribute("aiobs.accountability.originating_principal", "human_operator")
                reply = provider.chat(f"{agent} step", context=CONTEXT)
                set_llm_attributes(
                    span,
                    provider=provider.name,
                    model=reply.model,
                    input_tokens=reply.input_tokens,
                    output_tokens=reply.output_tokens,
                )
                run.add(agent, "act", tokens=reply.total_tokens)

        run.terminated = True
        run.verified = True
        root.set_attribute(Aiobs.HUMAN_REVIEW_OUTCOME, "upheld")

    return {
        "chain": [{"agent": a, "authorized_by": b} for a, b in CHAIN],
        "originating_principal": "human_operator",
        "unbroken": all(b for _, b in CHAIN),
        "verified": run.verified,
    }
