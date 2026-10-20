"""Unit tests: Chapter 13 decision-only judge and confidence cascade (Listing 13.3)."""

from __future__ import annotations

import pytest

from aiobs.evals import (
    CascadeEvaluator,
    Decision,
    DecisionQuestion,
    GroundednessEvaluator,
    JevJudge,
    MockDecisionJudge,
    cascade_attributes,
    preference_both_orders,
)
from chapters.ch13 import (
    FAITHFULNESS_QUESTION,
    JUDGE_FEES_USD_PER_1000,
    evaluate_rag_quality,
    evaluate_with_cascade,
)
from chapters.ch13.rag_quality import FIXTURES

# --- the decision contract ---


def test_a_decision_must_be_a_normalised_distribution_with_an_argmax_verdict():
    Decision("q", "yes", {"yes": 0.7, "no": 0.3}, judge="t")
    with pytest.raises(ValueError):
        Decision("q", "yes", {"yes": 0.7, "no": 0.7}, judge="t")
    with pytest.raises(ValueError):
        Decision("q", "no", {"yes": 0.7, "no": 0.3}, judge="t")
    with pytest.raises(ValueError):
        Decision("q", "maybe", {"yes": 0.7, "no": 0.3}, judge="t")


def test_confidence_is_the_maximum_label_probability():
    assert Decision("q", "no", {"yes": 0.2, "no": 0.8}, judge="t").confidence == 0.8


def test_a_noul_question_has_exactly_yes_and_no():
    DecisionQuestion("q", "noul", "Is it?", ("yes", "no"))
    with pytest.raises(ValueError):
        DecisionQuestion("q", "noul", "Is it?", ("true", "false"))
    with pytest.raises(ValueError):
        DecisionQuestion("q", "choice", "Pick", ("only",))


# --- the offline judge ---


def test_the_mock_judge_is_confident_at_the_extremes_and_unsure_in_the_middle():
    judge = MockDecisionJudge()
    same = judge.decide(
        {"response": "alpha beta gamma", "evidence": "alpha beta gamma"}, FAITHFULNESS_QUESTION
    )
    none = judge.decide(
        {"response": "alpha beta gamma", "evidence": "delta epsilon"}, FAITHFULNESS_QUESTION
    )
    half = judge.decide(
        {"response": "alpha beta gamma delta", "evidence": "alpha beta"}, FAITHFULNESS_QUESTION
    )
    assert same.label == "supported" and same.confidence > 0.99
    assert none.label == "hallucinated" and none.confidence > 0.99
    assert half.confidence == pytest.approx(0.5)


def test_the_mock_judge_is_deterministic():
    judge = MockDecisionJudge()
    state = {"response": FIXTURES[2].response, "evidence": FIXTURES[2].retrieved_contexts[0]}
    first = judge.decide(state, FAITHFULNESS_QUESTION)
    assert all(judge.decide(state, FAITHFULNESS_QUESTION) == first for _ in range(5))


# --- the cascade ---


def test_cascade_accepts_when_confident_and_escalates_when_unsure():
    report = evaluate_with_cascade()
    by_id = {o.sample_id: o for o in report.outcomes}
    assert not by_id["s1"].escalated and by_id["s1"].verdict == "supported"
    assert not by_id["s5"].escalated and by_id["s5"].verdict == "hallucinated"
    # The invented fee (s4) is exactly the case a cheap judge should not
    # decide alone.
    assert by_id["s4"].escalated
    assert report.escalated_count == 2
    assert report.escalation_rate == pytest.approx(2 / 6)


def test_every_accepted_verdict_agrees_with_the_fixture():
    report = evaluate_with_cascade()
    assert report.accepted_verdict_accuracy == 1.0
    assert report.verdict_accuracy == 1.0


def test_escalated_samples_take_the_listing_13_2_judges_score():
    """When the cascade is unsure, the result is the fallback's, not a blend."""
    report = evaluate_with_cascade()
    escalated = [o for o in report.outcomes if o.escalated]
    assert all(o.faithfulness in (0.0, 1.0) for o in escalated)


def test_hallucination_rate_is_still_the_complement_of_faithfulness():
    report = evaluate_with_cascade()
    assert report.hallucination_rate == pytest.approx(1.0 - report.faithfulness_mean)


def test_the_cascade_and_listing_13_2_agree_on_the_verdicts():
    """Same six samples, same four grounded and two not."""
    cascade = evaluate_with_cascade()
    listing = evaluate_rag_quality()
    supported = sum(o.verdict == "supported" for o in cascade.outcomes) / cascade.sample_count
    assert supported == pytest.approx(listing.faithfulness_mean)


def test_a_threshold_of_one_escalates_everything_and_reproduces_listing_13_2():
    report = evaluate_with_cascade(accept_threshold=1.0)
    assert report.escalated_count == report.sample_count
    assert report.faithfulness_mean == pytest.approx(evaluate_rag_quality().faithfulness_mean)


def test_the_threshold_is_bounded():
    with pytest.raises(ValueError):
        evaluate_with_cascade(accept_threshold=0.2)
    with pytest.raises(ValueError):
        evaluate_with_cascade(accept_threshold=1.1)


def test_fee_is_the_decision_fee_plus_the_escalated_share_of_the_generative_fee():
    report = evaluate_with_cascade()
    fees = JUDGE_FEES_USD_PER_1000
    expected = fees["decision"] + fees["generative"] * report.escalation_rate
    assert report.fee_usd_per_1000() == pytest.approx(expected, abs=1e-4)
    assert report.fee_ratio_to_generative_only() < 0.5


def test_an_empty_eval_raises():
    with pytest.raises(ValueError):
        evaluate_with_cascade(samples=[])


# --- what lands on the span ---


def test_result_detail_keeps_the_distribution_and_the_path_taken():
    evaluator = CascadeEvaluator(
        MockDecisionJudge(),
        GroundednessEvaluator(),
        FAITHFULNESS_QUESTION,
        positive_label="supported",
        accept_threshold=0.9,
    )
    accepted = evaluator.evaluate(FIXTURES[0].response, context=FIXTURES[0].retrieved_contexts[0])
    assert accepted.detail["escalated"] is False
    assert accepted.detail["fallback_evaluator"] is None
    assert set(accepted.detail["probabilities"]) == {"supported", "hallucinated"}

    escalated = evaluator.evaluate(FIXTURES[3].response, context=FIXTURES[3].retrieved_contexts[0])
    assert escalated.detail["escalated"] is True
    assert escalated.detail["fallback_evaluator"] == "groundedness"


def test_cascade_attributes_are_in_the_eval_namespace():
    evaluator = CascadeEvaluator(
        MockDecisionJudge(),
        GroundednessEvaluator(),
        FAITHFULNESS_QUESTION,
        positive_label="supported",
    )
    result = evaluator.evaluate(FIXTURES[3].response, context=FIXTURES[3].retrieved_contexts[0])
    attributes = cascade_attributes(result)
    assert attributes["eval.evaluator"] == "mock-decision-judge-v1"
    assert attributes["eval.escalated"] is True
    assert attributes["eval.fallback_evaluator"] == "groundedness"
    assert all(k.startswith("eval.") for k in attributes)


# --- the hosted adapter, driven through an injected transport ---


def _canned_transport(choice: str, p: float):
    calls: list[dict] = []

    def send(body: dict) -> dict:
        calls.append(body)
        name = next(iter(body["questions"]))
        other = next(label for label in body["questions"][name]["criteria"] if label != choice)
        return {
            "model": body["model"],
            "answers": {
                name: {
                    "type": "choice",
                    "choice": choice,
                    "probabilities": {choice: p, other: round(1 - p, 6)},
                }
            },
        }

    send.calls = calls  # type: ignore[attr-defined]
    return send


def test_jev_judge_builds_the_published_request_shape():
    transport = _canned_transport("supported", 0.93)
    judge = JevJudge(transport=transport)
    decision = judge.decide({"response": "r", "evidence": "e"}, FAITHFULNESS_QUESTION)
    body = transport.calls[0]
    assert body["model"] == "jev-1.13.0"
    assert body["state"] == {"response": "r", "evidence": "e"}
    assert body["questions"]["faithfulness"]["type"] == "choice"
    assert set(body["questions"]["faithfulness"]["criteria"]) == {"supported", "hallucinated"}
    assert decision.label == "supported" and decision.confidence == pytest.approx(0.93)
    assert decision.judge == "jev-1.13.0"


def test_jev_judge_without_a_key_or_transport_refuses_to_construct(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    with pytest.raises(ValueError):
        JevJudge()


def test_jev_judge_drops_into_the_cascade_unchanged():
    evaluator = CascadeEvaluator(
        JevJudge(transport=_canned_transport("hallucinated", 0.97)),
        GroundednessEvaluator(),
        FAITHFULNESS_QUESTION,
        positive_label="supported",
    )
    result = evaluator.evaluate("anything", context="whatever")
    assert result.detail["escalated"] is False
    assert result.score == pytest.approx(0.03)


# --- pairwise preference ---


class _PositionBiasedJudge:
    """Always prefers the first position. Averaging both orders cancels it."""

    name = "biased"

    def decide(self, state, question):
        return Decision(question.name, "A", {"A": 0.8, "B": 0.2}, judge=self.name)


def test_preference_both_orders_cancels_a_positional_bias():
    question = DecisionQuestion("pair", "choice", "Which is better?", ("A", "B"))
    p = preference_both_orders(_PositionBiasedJudge(), question, {}, [("A", "x"), ("B", "y")])
    assert p == pytest.approx(0.5)
