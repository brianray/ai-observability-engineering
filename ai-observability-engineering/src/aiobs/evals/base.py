"""Evaluator interface.

Chapter 1's third pitfall, in code: a metric is a claim that needs
periodic re-examination, not a fact. Every evaluator therefore carries the
version of the eval set it was calibrated against, and ``EvalResult``
records it. A score with no set version attached is not interpretable six
months later.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EvalResult:
    name: str
    score: float
    passed: bool
    threshold: float
    set_version: str
    detail: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.score <= 1.0:
            raise ValueError(f"{self.name}: score {self.score} outside [0, 1]")


class Evaluator(ABC):
    """Base class for output-quality evaluators."""

    name: str = "evaluator"
    #: True when a LOWER score is better (hallucination, toxicity).
    lower_is_better: bool = False

    def __init__(self, threshold: float, set_version: str = "v1") -> None:
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("threshold must be in [0, 1]")
        self.threshold = threshold
        self.set_version = set_version

    @abstractmethod
    def score(self, output: str, *, context: str | None = None, **kwargs: Any) -> float:
        """Return a raw score in [0, 1]."""

    def evaluate(self, output: str, *, context: str | None = None, **kwargs: Any) -> EvalResult:
        value = max(0.0, min(1.0, float(self.score(output, context=context, **kwargs))))
        passed = value <= self.threshold if self.lower_is_better else value >= self.threshold
        return EvalResult(
            name=self.name,
            score=round(value, 6),
            passed=passed,
            threshold=self.threshold,
            set_version=self.set_version,
        )
