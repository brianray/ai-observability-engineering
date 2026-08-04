"""Chapter 17: Accountability When Responsibility Is Delegated."""

from __future__ import annotations

from aiobs import AgentRun, Aiobs, Layer, MockProvider, Pillar, get_tracer
from aiobs.instrument import set_llm_attributes
from aiobs.semconv import GenAI

from .registry import example

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
