"""Chapter 14: Human Oversight Patterns."""

from __future__ import annotations

from aiobs import Aiobs, Layer, MockProvider, Pillar, default_suite, get_tracer
from aiobs.instrument import set_eval_attributes, set_llm_attributes

from .registry import example

CONTEXT = "Refund extensions apply only to active products purchased after March 2025"
REVIEW_THRESHOLD = 0.60


@example(
    chapter=14,
    key="review_queue_routing",
    title="Routing low-confidence outputs to a human, and recording the outcome",
    pillar=Pillar.RESPONSIBILITY,
    layer=Layer.APPLICATION_AND_ORCHESTRATION,
    listing="14.1",
)
def review_queue_routing() -> dict:
    """"A human is in the loop" is a claim. This is the evidence.

    Two attributes make the claim auditable: whether review was required,
    and what the reviewer decided. Without the second one you can only
    prove you generated work for someone, not that anyone did it.
    """
    tracer = get_tracer(__name__)
    provider = MockProvider()
    suite = default_suite()
    queued = 0
    auto_approved = 0
    overturned = 0

    with tracer.start_as_current_span("oversight_window") as root:
        root.set_attribute(Aiobs.PILLAR, Pillar.RESPONSIBILITY.value)
        root.set_attribute(Aiobs.LAYER, Layer.APPLICATION_AND_ORCHESTRATION.value)
        for i in range(20):
            question = f"claim {i} about refunds"
            context = CONTEXT if i % 3 else ""
            reply = provider.chat(question, context=context or None)
            scores = suite.scores(reply.text, context=context or None, prompt=question)
            needs_review = scores["groundedness"] < REVIEW_THRESHOLD

            with tracer.start_as_current_span("chat") as span:
                set_llm_attributes(
                    span,
                    provider=provider.name,
                    model=reply.model,
                    input_tokens=reply.input_tokens,
                    output_tokens=reply.output_tokens,
                )
                set_eval_attributes(span, scores, evaluator="heuristic-v1")
                span.set_attribute(Aiobs.HUMAN_REVIEW_REQUIRED, needs_review)
                if needs_review:
                    queued += 1
                    # Simulated reviewer decision, recorded on the span.
                    outcome = "overturned" if i % 2 else "upheld"
                    overturned += outcome == "overturned"
                    span.set_attribute(Aiobs.HUMAN_REVIEW_OUTCOME, outcome)
                else:
                    auto_approved += 1
                    span.set_attribute(Aiobs.HUMAN_REVIEW_OUTCOME, "not_required")
        root.set_attribute("aiobs.oversight.queued", queued)

    return {
        "total": 20,
        "queued_for_review": queued,
        "auto_approved": auto_approved,
        "overturned_by_reviewer": overturned,
        "overturn_rate": round(overturned / queued, 4) if queued else 0.0,
        "why_overturn_rate_matters": "a rate near zero means the queue is theater",
    }
