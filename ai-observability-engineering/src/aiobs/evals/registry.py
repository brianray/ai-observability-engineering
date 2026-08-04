"""Evaluator registry and suite runner."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from .base import EvalResult, Evaluator
from .heuristics import (
    GroundednessEvaluator,
    HallucinationEvaluator,
    RelevanceEvaluator,
)

_REGISTRY: dict[str, Callable[..., Evaluator]] = {}


def register(name: str, factory: Callable[..., Evaluator]) -> None:
    if name in _REGISTRY:
        raise ValueError(f"evaluator {name!r} already registered")
    _REGISTRY[name] = factory


def registry() -> dict[str, Callable[..., Evaluator]]:
    return dict(_REGISTRY)


register("groundedness", GroundednessEvaluator)
register("hallucination", HallucinationEvaluator)
register("relevance", RelevanceEvaluator)


@dataclass
class EvalSuite:
    """A named set of evaluators run together against one output."""

    evaluators: list[Evaluator] = field(default_factory=list)
    set_version: str = "v1"

    def add(self, evaluator: Evaluator) -> EvalSuite:
        self.evaluators.append(evaluator)
        return self

    def run(
        self, output: str, *, context: str | None = None, prompt: str = ""
    ) -> dict[str, EvalResult]:
        return {
            e.name: e.evaluate(output, context=context, prompt=prompt) for e in self.evaluators
        }

    def scores(
        self, output: str, *, context: str | None = None, prompt: str = ""
    ) -> dict[str, float]:
        return {
            name: r.score for name, r in self.run(output, context=context, prompt=prompt).items()
        }

    def all_passed(self, output: str, *, context: str | None = None, prompt: str = "") -> bool:
        return all(r.passed for r in self.run(output, context=context, prompt=prompt).values())


def default_suite(set_version: str = "v1") -> EvalSuite:
    return EvalSuite(
        evaluators=[
            GroundednessEvaluator(set_version=set_version),
            HallucinationEvaluator(set_version=set_version),
            RelevanceEvaluator(set_version=set_version),
        ],
        set_version=set_version,
    )
