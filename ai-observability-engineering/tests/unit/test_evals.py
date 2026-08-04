"""Unit tests: evaluators."""

import pytest

from aiobs.evals import (
    EvalResult,
    GroundednessEvaluator,
    HallucinationEvaluator,
    RelevanceEvaluator,
    default_suite,
)

CONTEXT = "Refund extensions apply only to active products purchased after March 2025."


def test_groundedness_rewards_answers_drawn_from_the_context():
    evaluator = GroundednessEvaluator()
    grounded = evaluator.score(
        "Refund extensions apply to active products purchased after March 2025.",
        context=CONTEXT,
    )
    invented = evaluator.score("Bananas ripen faster in paper bags.", context=CONTEXT)
    assert grounded > 0.8
    assert invented < 0.2


def test_groundedness_without_context_is_zero_not_one():
    """An ungrounded system cannot be scored for groundedness."""
    assert GroundednessEvaluator().score("anything at all", context=None) == 0.0


def test_hallucination_ranks_confident_wrong_above_hedged_wrong():
    """Fluency is not correctness. Confidence makes an ungrounded answer worse."""
    evaluator = HallucinationEvaluator()
    confident = evaluator.score("It always applies, guaranteed.", context=CONTEXT)
    hedged = evaluator.score("It might possibly apply.", context=CONTEXT)
    assert confident > hedged


def test_hallucination_is_low_for_a_grounded_answer():
    score = HallucinationEvaluator().score(
        "Refund extensions apply only to active products purchased after March 2025.",
        context=CONTEXT,
    )
    assert score < 0.2


def test_lower_is_better_flag_inverts_the_pass_condition():
    result = HallucinationEvaluator(threshold=0.2).evaluate(
        "Refund extensions apply only to active products purchased after March 2025.",
        context=CONTEXT,
    )
    assert result.passed
    assert HallucinationEvaluator.lower_is_better is True


def test_relevance_needs_the_prompt():
    evaluator = RelevanceEvaluator()
    assert evaluator.score("some answer", prompt="") == 0.0
    assert evaluator.score("refund extensions", prompt="refund extensions") > 0.9


def test_scores_are_clamped_to_the_unit_interval():
    class Rogue(GroundednessEvaluator):
        def score(self, output, *, context=None, **kwargs):
            return 42.0

    assert Rogue().evaluate("x", context=CONTEXT).score == 1.0


def test_eval_result_rejects_out_of_range_scores():
    with pytest.raises(ValueError):
        EvalResult(name="x", score=1.5, passed=True, threshold=0.5, set_version="v1")


def test_threshold_must_be_a_probability():
    with pytest.raises(ValueError):
        GroundednessEvaluator(threshold=1.4)


def test_suite_records_the_eval_set_version():
    """A score with no set version is not interpretable six months later."""
    results = default_suite(set_version="v7").run("text", context=CONTEXT, prompt="text")
    assert {r.set_version for r in results.values()} == {"v7"}


def test_suite_returns_one_result_per_evaluator():
    results = default_suite().run("text", context=CONTEXT, prompt="text")
    assert set(results) == {"groundedness", "hallucination", "relevance"}
