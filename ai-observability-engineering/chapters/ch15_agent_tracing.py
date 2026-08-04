"""Chapter 15: Tracing Multi-Agent Systems."""

from __future__ import annotations

from aiobs import AgentRun, Aiobs, Layer, MockProvider, Operation, Pillar, get_tracer
from aiobs.agents import classify
from aiobs.instrument import set_llm_attributes
from aiobs.semconv import GenAI

from .registry import example

CONTEXT = "Refund extensions apply only to active products purchased after March 2025"
PLAN = [
    ("planner", "decompose"),
    ("researcher", "search"),
    ("researcher", "read"),
    ("writer", "draft"),
    ("critic", "verify"),
]


@example(
    chapter=15,
    key="agent_handoff_trace",
    title="One trace across five agent handoffs",
    pillar=Pillar.PERFORMANCE,
    layer=Layer.APPLICATION_AND_ORCHESTRATION,
    listing="15.2",
)
def agent_handoff_trace() -> dict:
    """Every handoff is a span, and every span stays in the same trace.

    Context loss at a handoff is MAST FM-1.4, and it looks like a
    perfectly healthy set of unrelated traces if you do not propagate.
    """
    tracer = get_tracer(__name__)
    provider = MockProvider()
    run = AgentRun(task="summarize the refund policy change")

    with tracer.start_as_current_span("invoke_agent orchestrator") as root:
        root.set_attribute(GenAI.OPERATION_NAME, Operation.INVOKE_AGENT)
        root.set_attribute(GenAI.AGENT_NAME, "orchestrator")
        root.set_attribute(GenAI.PROVIDER_NAME, "internal")
        root.set_attribute(Aiobs.PILLAR, Pillar.PERFORMANCE.value)
        root.set_attribute(Aiobs.LAYER, Layer.APPLICATION_AND_ORCHESTRATION.value)

        for agent, action in PLAN:
            with tracer.start_as_current_span(f"invoke_agent {agent}") as span:
                span.set_attribute(GenAI.AGENT_NAME, agent)
                span.set_attribute("aiobs.agent.action", action)
                # The agent span wraps a model call; the model attributes
                # belong on the child, so this span records the handoff.
                reply = provider.chat(f"{agent}:{action}", context=CONTEXT)
                span.set_attribute(GenAI.OPERATION_NAME, Operation.INVOKE_AGENT)
                span.set_attribute(GenAI.PROVIDER_NAME, provider.name)
                with tracer.start_as_current_span(f"chat {provider.model}") as child:
                    set_llm_attributes(
                        child,
                        provider=provider.name,
                        model=reply.model,
                        input_tokens=reply.input_tokens,
                        output_tokens=reply.output_tokens,
                    )
                run.add(agent, action, reply.text, tokens=reply.total_tokens)

        run.terminated = True
        run.verified = True
        root.set_attribute(Aiobs.AGENT_HANDOFF_DEPTH, run.handoff_depth)
        root.set_attribute("aiobs.agent.total_tokens", run.total_tokens)

    return {
        "steps": len(run.steps),
        "handoff_depth": run.handoff_depth,
        "total_tokens": run.total_tokens,
        "mast_failure_modes": [m.value for m in classify(run)],
    }
