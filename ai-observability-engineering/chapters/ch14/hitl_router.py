"""Routing work to humans, and proving you did (Listing 14.1).

The routing rule has three branches and they are not interchangeable:

``mandatory_class``
    Some decisions go to a human regardless of how confident the model
    is. Confidence is not a defence for a decision class the regulation
    says a person must make, so this branch is checked first and does not
    consult the score at all.

``below_threshold``
    The model is not confident enough. This is the branch people build.

``sampled_audit``
    A fraction of high-confidence work goes to a human anyway. This is
    the branch people skip, and it is the only one that can ever tell you
    your threshold is wrong: without it you only ever review the cases
    the model already doubted, so a confidently wrong model looks
    perfect forever.

The sampler is seeded, because an audit rate you cannot reproduce is an
audit rate you cannot evidence.
"""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field

from aiobs import Aiobs, get_tracer

REASON_MANDATORY = "mandatory_class"
REASON_BELOW_THRESHOLD = "below_threshold"
REASON_SAMPLED_AUDIT = "sampled_audit"
REASON_AUTO = "auto_approved"

#: Decision classes a human must see whatever the model thinks.
MANDATORY_CLASSES: frozenset[str] = frozenset(
    {"adverse_action", "credit_decline", "account_closure"}
)

DEFAULT_CONFIDENCE_THRESHOLD = 0.80
DEFAULT_AUDIT_SAMPLE_RATE = 0.05

QUEUE_SPECIALIST = "specialist_review"
QUEUE_GENERAL = "general_review"
QUEUE_AUDIT = "audit_sample"


@dataclass(frozen=True)
class Recommendation:
    recommendation_id: str
    decision_class: str
    confidence: float


@dataclass(frozen=True)
class RoutingResult:
    routed: bool
    reason: str
    queue: str | None
    confidence: float


class MockQueue:
    """Stands in for the review queue. Records what it was handed."""

    def __init__(self) -> None:
        self.items: list[tuple[str, Recommendation]] = []

    def enqueue(self, queue: str, recommendation: Recommendation) -> None:
        self.items.append((queue, recommendation))

    def depth(self, queue: str) -> int:
        return sum(1 for q, _ in self.items if q == queue)


@dataclass
class RouteCounter:
    """Stands in for a Prometheus counter, with the labels pinned."""

    counts: Counter[tuple[str, str]] = field(default_factory=Counter)

    def increment(self, destination: str, reason: str) -> None:
        self.counts[(destination, reason)] += 1

    def get(self, destination: str, reason: str) -> int:
        return self.counts[(destination, reason)]


@dataclass
class HitlRouter:
    queue: MockQueue
    counter: RouteCounter
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD
    audit_sample_rate: float = DEFAULT_AUDIT_SAMPLE_RATE
    seed: int = 1729
    _rng: random.Random = field(init=False)

    def __post_init__(self) -> None:
        if not 0.0 <= self.audit_sample_rate <= 1.0:
            raise ValueError("audit_sample_rate must be a probability")
        self._rng = random.Random(self.seed)

    def should_sample(self) -> bool:
        """Seeded audit sampling. Reproducible across runs."""
        return self._rng.random() < self.audit_sample_rate

    def select_queue(self, recommendation: Recommendation, reason: str) -> str:
        if reason == REASON_SAMPLED_AUDIT:
            return QUEUE_AUDIT
        if recommendation.decision_class in MANDATORY_CLASSES:
            return QUEUE_SPECIALIST
        return QUEUE_GENERAL

    def enqueue(self, queue: str, recommendation: Recommendation) -> None:
        self.queue.enqueue(queue, recommendation)

    def route(self, recommendation: Recommendation) -> RoutingResult:
        tracer = get_tracer(__name__)
        with tracer.start_as_current_span("hitl.route") as span:
            # Mandatory first, and without consulting confidence: a
            # confident model is not a defence for a decision class a
            # person is required to make.
            if recommendation.decision_class in MANDATORY_CLASSES:
                reason = REASON_MANDATORY
            elif recommendation.confidence < self.confidence_threshold:
                reason = REASON_BELOW_THRESHOLD
            elif self.should_sample():
                reason = REASON_SAMPLED_AUDIT
            else:
                reason = REASON_AUTO

            routed = reason != REASON_AUTO
            queue = self.select_queue(recommendation, reason) if routed else None

            span.set_attribute(Aiobs.HITL_ROUTED, routed)
            span.set_attribute(Aiobs.HITL_REASON, reason)
            span.set_attribute(Aiobs.HITL_QUEUE, queue or "none")
            span.set_attribute(Aiobs.HITL_CONFIDENCE, recommendation.confidence)

            if routed:
                self.enqueue(queue, recommendation)  # type: ignore[arg-type]
            self.counter.increment(queue or "auto", reason)

            return RoutingResult(routed, reason, queue, recommendation.confidence)
