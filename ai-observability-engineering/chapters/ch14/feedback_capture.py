"""Capturing what the reviewer did, and what may be learned from it (Listing 14.2).

Two separate destinations, and conflating them is the mistake this code
exists to prevent.

**The audit log** takes every oversight action, unconditionally. That a
human looked and upheld the model is exactly as auditable as an override,
and a log that only records disagreements cannot evidence that review
happened at all.

**The feedback dataset** takes very little. An override is a correction
only if the reviewer was in a position to make one, and only if someone
has said so. So a record reaches training when two things hold: the
outcome actually carries new information (``modify`` or ``override``, not
``uphold``), and a human has marked it ``fit_for_training``. Training on
every override is how a reviewer's bad afternoon becomes a model update.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from chapters.ch12 import AuditLogger

EVENT_TYPE = "oversight_action"


class ReviewOutcome(str, Enum):
    UPHOLD = "uphold"
    MODIFY = "modify"
    OVERRIDE = "override"


#: Outcomes that carry new information. An upheld recommendation tells
#: you the model was right, which is worth auditing and worth almost
#: nothing as a training gradient.
INFORMATIVE_OUTCOMES: frozenset[ReviewOutcome] = frozenset(
    {ReviewOutcome.MODIFY, ReviewOutcome.OVERRIDE}
)

#: The payload keys every oversight_action event carries. Pinned so a
#: later edit cannot silently drop one.
PAYLOAD_KEYS: tuple[str, ...] = (
    "event_type",
    "recommendation_id",
    "decision_class",
    "queue",
    "reviewer_role",
    "outcome",
    "review_seconds",
    "model_confidence",
    "fit_for_training",
    "trace_id",
)


@dataclass(frozen=True)
class OversightAction:
    recommendation_id: str
    decision_class: str
    queue: str
    reviewer_role: str
    outcome: ReviewOutcome
    assigned_at: datetime
    decided_at: datetime
    model_confidence: float
    #: Set by a human, not inferred. Defaults to False so the safe path
    #: is the default path.
    fit_for_training: bool = False
    trace_id: str = ""

    @property
    def review_seconds(self) -> float:
        seconds = (self.decided_at - self.assigned_at).total_seconds()
        if seconds < 0:
            raise ValueError("decided_at precedes assigned_at")
        return round(seconds, 3)

    def to_payload(self) -> dict:
        return {
            "event_type": EVENT_TYPE,
            "recommendation_id": self.recommendation_id,
            "decision_class": self.decision_class,
            "queue": self.queue,
            "reviewer_role": self.reviewer_role,
            "outcome": self.outcome.value,
            "review_seconds": self.review_seconds,
            "model_confidence": self.model_confidence,
            "fit_for_training": self.fit_for_training,
            "trace_id": self.trace_id,
        }


class FeedbackDataset:
    """What may be learned from. Deliberately harder to get into than the log."""

    def __init__(self) -> None:
        self.records: list[dict] = []

    def add(self, action: OversightAction) -> None:
        self.records.append(action.to_payload())

    def __len__(self) -> int:
        return len(self.records)


class FeedbackCapture:
    """Writes to the Chapter 12 audit log, and selectively to training."""

    def __init__(self, audit: AuditLogger, dataset: FeedbackDataset | None = None) -> None:
        self._audit = audit
        self.dataset = dataset or FeedbackDataset()

    def capture(self, action: OversightAction) -> dict:
        """Log unconditionally; admit to the dataset only if both gates pass."""
        payload = action.to_payload()
        self._audit.append(payload)

        if action.outcome in INFORMATIVE_OUTCOMES and action.fit_for_training:
            self.dataset.add(action)
        return payload
