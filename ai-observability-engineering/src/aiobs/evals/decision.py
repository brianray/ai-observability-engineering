"""Decision-only judges and the confidence cascade (Chapter 13).

Chapter 3 defined an evaluation as a reference, a scoring function, and a
place to put the result. Every scoring function so far has either been a
heuristic or a generative model asked to write a verdict. This module adds
a third kind: a *decision model*, which takes structured state and a
bounded question and returns a typed decision with a probability over the
allowed labels, and no prose at all.

Three things the code insists on.

**The judge is a protocol, not a vendor.** ``DecisionJudge`` is the
interface; ``MockDecisionJudge`` is the deterministic offline
implementation the book's examples and tests run against; ``JevJudge``
is an adapter for one hosted instance of the category (TypeSafe JEV).
Swap the implementation and the instrumentation does not move, which is
the same argument Listing 3.4 and Listing 13.2 made.

**Confidence is an escalation signal, not a certificate.** The cascade
accepts the decision model's verdict when its maximum label probability
clears a threshold and otherwise escalates to a stronger (and dearer)
fallback judge. The threshold is a named parameter chosen on local data,
never a constant someone read off a benchmark table.

**Record the distribution, not the argmax.** ``Decision.probabilities``
is kept in full and ``EvalResult.detail`` carries it, with the confidence
and the escalation flag, onto the span. A score stored as a boolean
cannot be re-thresholded later; a distribution can.

Verified against the request/response shape published for ``jev-1.13.0``
in Li et al. (2026), Figure 6. The hosted API can change; check the
provider's reference before relying on ``JevJudge`` outside this
repository.
"""

from __future__ import annotations

import json
import math
import os
import re
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from .base import EvalResult, Evaluator
from .heuristics import GroundednessEvaluator

QuestionKind = Literal["noul", "choice", "score"]

#: Default acceptance threshold on the maximum label probability. Li et
#: al. (2026) report that at 0.9 a cascade to a frontier judge retained
#: about 99 percent of that judge's accuracy on preference and factuality
#: tasks. That is a published starting point, not your threshold: validate
#: it on a local selection set, as Section 13.3 insists.
DEFAULT_ACCEPT_THRESHOLD = 0.90


@dataclass(frozen=True)
class DecisionQuestion:
    """One bounded question for a decision judge.

    ``labels`` is the closed set of allowed answers, in order. For a
    ``noul`` question it is ("yes", "no"); for a ``score`` question it is
    the ordered rubric levels, worst to best.
    """

    name: str
    kind: QuestionKind
    instructions: str
    labels: tuple[str, ...]
    criteria: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind == "noul" and tuple(self.labels) != ("yes", "no"):
            raise ValueError("a noul question's labels are exactly ('yes', 'no')")
        if len(self.labels) < 2:
            raise ValueError("a decision needs at least two labels")
        if len(set(self.labels)) != len(self.labels):
            raise ValueError("labels must be distinct")


@dataclass(frozen=True)
class Decision:
    """A typed verdict with its probability distribution.

    ``confidence`` is the maximum label probability. Li et al. (2026)
    found it to track the provider's native confidence statistic with
    Spearman correlation above 0.94 on every public task they measured,
    so the book uses the one quantity every decision model can supply.
    """

    question: str
    label: str
    probabilities: Mapping[str, float]
    judge: str

    def __post_init__(self) -> None:
        total = sum(self.probabilities.values())
        if abs(total - 1.0) > 0.025:
            raise ValueError(f"{self.question}: probabilities sum to {total:.3f}, not 1")
        if self.label not in self.probabilities:
            raise ValueError(f"{self.question}: label {self.label!r} is not an allowed label")
        if self.probabilities[self.label] < max(self.probabilities.values()) - 1e-9:
            raise ValueError(f"{self.question}: verdict is not the highest-probability label")

    @property
    def confidence(self) -> float:
        return max(self.probabilities.values())


class DecisionJudge(Protocol):
    """The interface. State in, typed decision out, no rationale."""

    name: str

    def decide(self, state: Mapping[str, str], question: DecisionQuestion) -> Decision: ...


# --- the offline judge -------------------------------------------------------

_TOKEN = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?")

#: Steepness of the overlap-to-probability curve. Chosen so that full
#: overlap and near-zero overlap come out confident (above 0.99 and below
#: 0.02) while overlap between 0.4 and 0.65 lands under the default
#: acceptance threshold and escalates.
_SHARPNESS = 12.0


def _content_words(text: str) -> set[str]:
    return {w for w in _TOKEN.findall(text.lower()) if len(w) > 2}


class MockDecisionJudge:
    """A decision judge with no model behind it.

    Answers a two-label question about whether ``state["response"]`` is
    supported by ``state["evidence"]`` from content-word overlap, and
    turns the overlap into a probability that is deliberately *not*
    always confident. That spread is the point: a cascade demonstrated
    on a judge that is always sure demonstrates nothing.

    Do not ship this as a production judge. Its job is to make the
    cascade in Listing 13.3 run deterministically in CI.
    """

    name = "mock-decision-judge-v1"

    def decide(self, state: Mapping[str, str], question: DecisionQuestion) -> Decision:
        if len(question.labels) != 2:
            raise ValueError(f"{self.name} answers two-label questions only")
        response = _content_words(state.get("response", ""))
        evidence = _content_words(state.get("evidence", ""))
        overlap = len(response & evidence) / len(response) if response else 0.0
        # A logistic curve on the overlap: clear cases come out confident,
        # partial overlap comes out uncertain. Overlap 1.0 gives the first
        # label about 0.998; 0.5 gives exactly 0.5; 0.17 gives about 0.02.
        p_first = 1.0 / (1.0 + math.exp(-_SHARPNESS * (overlap - 0.5)))
        first, second = question.labels
        probabilities = {first: round(p_first, 4), second: round(1.0 - p_first, 4)}
        label = first if probabilities[first] >= probabilities[second] else second
        return Decision(question.name, label, probabilities, judge=self.name)


# --- the hosted judge --------------------------------------------------------

#: A transport takes a JSON-serialisable request body and returns the
#: parsed response body. Injected so the adapter can be exercised without
#: a key, a network, or a dependency on the provider's SDK.
Transport = Callable[[dict[str, Any]], dict[str, Any]]


def _http_transport(endpoint: str, api_key: str) -> Transport:
    def send(body: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    return send


class JevJudge:
    """Adapter for TypeSafe JEV, one hosted decision model.

    The request body mirrors the published shape: ``model``, a ``state``
    mapping of named fields, and a ``questions`` mapping whose values
    carry ``type``, ``instructions`` and per-label ``criteria``. The
    response carries ``answers.<name>.choice`` and
    ``answers.<name>.probabilities``.

    Nothing here is exercised against the live service in CI. The test
    suite drives this class through an injected transport, which is also
    how you would record and replay real responses for a regression set.
    """

    DEFAULT_ENDPOINT = "https://api.typesafe.ai/v1/decide"

    def __init__(
        self,
        model: str = "jev-1.13.0",
        *,
        transport: Transport | None = None,
        endpoint: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.model = model
        self.name = model
        if transport is None:
            key = api_key or os.environ.get("TYPESAFE_API_KEY")
            if not key:
                raise ValueError(
                    "JevJudge needs a transport or an API key (TYPESAFE_API_KEY); "
                    "the book's examples use MockDecisionJudge instead"
                )
            transport = _http_transport(endpoint or self.DEFAULT_ENDPOINT, key)
        self._transport = transport

    def request_body(self, state: Mapping[str, str], question: DecisionQuestion) -> dict[str, Any]:
        criteria = dict(question.criteria) or {label: label for label in question.labels}
        return {
            "model": self.model,
            "state": dict(state),
            "questions": {
                question.name: {
                    "type": question.kind,
                    "instructions": question.instructions,
                    "criteria": criteria,
                }
            },
        }

    def decide(self, state: Mapping[str, str], question: DecisionQuestion) -> Decision:
        answer = self._transport(self.request_body(state, question))["answers"][question.name]
        probabilities = {label: float(answer["probabilities"][label]) for label in question.labels}
        return Decision(question.name, str(answer["choice"]), probabilities, judge=self.model)


# --- the cascade -------------------------------------------------------------

#: The fallback judge in the cascade. Any Evaluator will do; in the book
#: it stands in for the RAGAS-backed judge of Listing 13.2, which is a
#: generative model call and therefore the expensive stage.
Fallback = Evaluator


class CascadeEvaluator(Evaluator):
    """Accept when confident, escalate when unsure.

    ``score`` returns the probability the decision judge assigns to
    ``positive_label`` when its confidence clears ``accept_threshold``,
    and the fallback evaluator's score otherwise. ``evaluate`` records
    which path was taken in ``EvalResult.detail`` so the span, and every
    dashboard built on it, can tell the two judges apart.
    """

    name = "cascade"

    def __init__(
        self,
        judge: DecisionJudge,
        fallback: Fallback,
        question: DecisionQuestion,
        *,
        positive_label: str,
        accept_threshold: float = DEFAULT_ACCEPT_THRESHOLD,
        threshold: float = 0.6,
        set_version: str = "v1",
    ) -> None:
        super().__init__(threshold, set_version)
        if not 0.5 <= accept_threshold <= 1.0:
            raise ValueError("accept_threshold must be in [0.5, 1]")
        if positive_label not in question.labels:
            raise ValueError(f"{positive_label!r} is not one of {question.labels}")
        self.judge = judge
        self.fallback = fallback
        self.question = question
        self.positive_label = positive_label
        self.accept_threshold = accept_threshold
        self.last_decision: Decision | None = None
        self.last_escalated: bool | None = None

    def score(self, output: str, *, context: str | None = None, **kwargs: Any) -> float:
        decision = self.judge.decide({"response": output, "evidence": context or ""}, self.question)
        self.last_decision = decision
        self.last_escalated = decision.confidence < self.accept_threshold
        if self.last_escalated:
            return self.fallback.score(output, context=context, **kwargs)
        return decision.probabilities[self.positive_label]

    def evaluate(self, output: str, *, context: str | None = None, **kwargs: Any) -> EvalResult:
        result = super().evaluate(output, context=context, **kwargs)
        decision = self.last_decision
        assert decision is not None  # score() always sets it
        detail = {
            "judge": decision.judge,
            "confidence": round(decision.confidence, 6),
            "probabilities": dict(decision.probabilities),
            "escalated": bool(self.last_escalated),
            "fallback_evaluator": self.fallback.name if self.last_escalated else None,
        }
        return EvalResult(
            name=result.name,
            score=result.score,
            passed=result.passed,
            threshold=result.threshold,
            set_version=result.set_version,
            detail=detail,
        )


def cascade_attributes(result: EvalResult) -> dict[str, Any]:
    """Span attributes for a cascade result, under the ``eval.`` namespace.

    Kept as a plain mapping so the chapter listing can show exactly what
    lands on the span, and so a collector transform can rename it.
    """
    detail = result.detail
    attributes: dict[str, Any] = {
        "eval.evaluator": detail["judge"],
        "eval.confidence": float(detail["confidence"]),
        "eval.escalated": bool(detail["escalated"]),
    }
    if detail.get("fallback_evaluator"):
        attributes["eval.fallback_evaluator"] = detail["fallback_evaluator"]
    return attributes


# --- pairwise preference, both orders ---------------------------------------


def preference_both_orders(
    judge: DecisionJudge,
    question: DecisionQuestion,
    state: Mapping[str, str],
    candidates: Sequence[tuple[str, str]],
) -> float:
    """Probability that candidate A is preferred, averaged over both orders.

    Li et al. (2026) found that reversing candidate order changed 3 to 11
    percent of a decision model's pairwise verdicts. Judge both orders
    and average the aligned probability before gating on it:

        p(A) = 1/2 * [ p_first(A, B) + 1 - p_first(B, A) ]

    ``candidates`` is ``[("A", text_a), ("B", text_b)]`` and ``question``
    must use the labels ``("A", "B")``.
    """
    if tuple(question.labels) != ("A", "B") or len(candidates) != 2:
        raise ValueError("preference_both_orders expects two candidates labeled A and B")
    (_, text_a), (_, text_b) = candidates
    forward = judge.decide({**state, "A": text_a, "B": text_b}, question)
    reverse = judge.decide({**state, "A": text_b, "B": text_a}, question)
    return 0.5 * (forward.probabilities["A"] + 1.0 - reverse.probabilities["A"])


def default_groundedness_fallback(set_version: str = "v1") -> Evaluator:
    """The fallback the book uses when it does not want a live judge."""
    return GroundednessEvaluator(set_version=set_version)
