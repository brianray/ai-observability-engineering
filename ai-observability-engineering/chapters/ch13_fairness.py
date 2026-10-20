"""Chapter 13: Fairness and Quality as Monitored Metrics."""

from __future__ import annotations

from aiobs import Aiobs, Layer, MockProvider, Pillar, default_suite, get_tracer
from aiobs.evals import CascadeEvaluator, MockDecisionJudge, cascade_attributes
from aiobs.instrument import set_eval_attributes, set_llm_attributes
from aiobs.providers import FailureMode

from .ch13.cascade_judge import FAITHFULNESS_QUESTION, ListingJudgeEvaluator
from .ch13.rag_quality import FIXTURES
from .registry import example

COHORTS = ("cohort_a", "cohort_b")
CONTEXT = "Refund extensions apply only to active products purchased after March 2025"


@example(
    chapter=13,
    key="quality_parity_across_cohorts",
    title="Quality is not one number, it is a distribution across groups",
    pillar=Pillar.RESPONSIBILITY,
    layer=Layer.MODEL_AND_INFERENCE,
    listing="13.2",
)
def quality_parity_across_cohorts() -> dict:
    """An aggregate groundedness of 0.85 can hide 0.95 for one group and
    0.55 for another. The aggregate is the number that lets a fairness
    problem run for a quarter."""
    tracer = get_tracer(__name__)
    suite = default_suite()
    providers = {
        "cohort_a": MockProvider(),
        "cohort_b": MockProvider(failure_mode=FailureMode.UNGROUNDED),
    }
    per_cohort: dict[str, list[float]] = {c: [] for c in COHORTS}

    with tracer.start_as_current_span("fairness_check") as root:
        root.set_attribute(Aiobs.PILLAR, Pillar.RESPONSIBILITY.value)
        root.set_attribute(Aiobs.LAYER, Layer.MODEL_AND_INFERENCE.value)
        for cohort in COHORTS:
            provider = providers[cohort]
            for i in range(20):
                question = f"question {i} about refunds"
                reply = provider.chat(question, context=CONTEXT)
                scores = suite.scores(reply.text, context=CONTEXT, prompt=question)
                per_cohort[cohort].append(scores["groundedness"])
                with tracer.start_as_current_span("chat") as span:
                    span.set_attribute("aiobs.cohort", cohort)
                    set_llm_attributes(
                        span,
                        provider=provider.name,
                        model=reply.model,
                        input_tokens=reply.input_tokens,
                        output_tokens=reply.output_tokens,
                    )
                    set_eval_attributes(span, scores, evaluator="heuristic-v1")

        means = {c: round(sum(v) / len(v), 4) for c, v in per_cohort.items()}
        aggregate = round(sum(sum(v) for v in per_cohort.values()) / 40, 4)
        gap = round(max(means.values()) - min(means.values()), 4)
        root.set_attribute("aiobs.fairness.groundedness_gap", gap)
        root.set_attribute("aiobs.fairness.aggregate", aggregate)

    return {
        "aggregate_groundedness": aggregate,
        "per_cohort": means,
        "gap": gap,
        "gap_visible_in_aggregate": False,
        "threshold_breached": gap > 0.10,
    }


@example(
    chapter=13,
    key="confidence_cascade_eval",
    title="A decision-only judge, accepted when confident and escalated when unsure",
    pillar=Pillar.RESPONSIBILITY,
    layer=Layer.MODEL_AND_INFERENCE,
    listing="13.3",
)
def confidence_cascade_eval() -> dict:
    """The judge call does not have to generate text to produce a verdict.

    Every sample is scored by a decision model that returns a probability.
    Confident verdicts are accepted and recorded; uncertain ones go to the
    Listing 13.2 judge. The span records which path each sample took, so
    the two judges can be told apart on a dashboard rather than averaged.
    """
    tracer = get_tracer(__name__)
    evaluator = CascadeEvaluator(
        judge=MockDecisionJudge(),
        fallback=ListingJudgeEvaluator(),
        question=FAITHFULNESS_QUESTION,
        positive_label="supported",
        accept_threshold=0.90,
    )
    escalated = 0
    faithfulness: list[float] = []

    with tracer.start_as_current_span("cascade_eval") as root:
        root.set_attribute(Aiobs.PILLAR, Pillar.RESPONSIBILITY.value)
        root.set_attribute(Aiobs.LAYER, Layer.MODEL_AND_INFERENCE.value)
        for sample in FIXTURES:
            result = evaluator.evaluate(
                sample.response,
                context=" ".join(sample.retrieved_contexts),
                sample=sample,
            )
            faithfulness.append(result.score)
            escalated += result.detail["escalated"]
            with tracer.start_as_current_span("eval.judge") as span:
                span.set_attribute("aiobs.sample_id", sample.sample_id)
                set_eval_attributes(span, {"groundedness": result.score})
                for key, value in cascade_attributes(result).items():
                    span.set_attribute(key, value)
        root.set_attribute("aiobs.eval.escalation_rate", escalated / len(FIXTURES))

    mean = round(sum(faithfulness) / len(faithfulness), 4)
    return {
        "samples": len(FIXTURES),
        "escalated": escalated,
        "escalation_rate": round(escalated / len(FIXTURES), 4),
        "faithfulness_mean": mean,
        "hallucination_rate": round(1.0 - mean, 4),
        "why_the_flag_matters": "a verdict without its judge's name is a number you cannot audit",
    }
