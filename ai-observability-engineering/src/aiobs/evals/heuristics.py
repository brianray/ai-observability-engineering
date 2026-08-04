"""Heuristic evaluators.

Deliberately simple and deliberately offline, so the book's examples run
deterministically without a judge model or an API key. In production you
swap the implementation, keep the interface, and the instrumentation does
not move. That substitutability is the point of the interface.

Do not ship these heuristics as production quality gates.
"""

from __future__ import annotations

import re
from typing import Any

from .base import Evaluator

_HEDGES = re.compile(r"\b(might|maybe|possibly|i think|probably|it seems|likely)\b", re.IGNORECASE)
_ABSOLUTES = re.compile(
    r"\b(always|never|guaranteed|definitely|certainly|without a doubt)\b", re.IGNORECASE
)
_WORD = re.compile(r"[a-z0-9']+")
_STOPWORDS = frozenset(
    ["a", "an", "and", "are", "as", "at", "be", "by", "does", "do", "for", "from", "in", "is", "it", "its", "of", "on", "or", "that", "the", "this", "to", "was", "were", "will", "with", "you", "your"]
)


def _tokens(text: str) -> set[str]:
    return {t for t in _WORD.findall(text.lower()) if t not in _STOPWORDS}


class GroundednessEvaluator(Evaluator):
    """Overlap between the answer's content words and the retrieved context.

    A crude proxy for "is this answer supported by what we retrieved."
    Returns 0.0 when there is no context at all, which is the honest
    answer: an ungrounded system cannot be scored for groundedness.
    """

    name = "groundedness"

    def __init__(self, threshold: float = 0.6, set_version: str = "v1") -> None:
        super().__init__(threshold, set_version)

    def score(self, output: str, *, context: str | None = None, **_: Any) -> float:
        if not context:
            return 0.0
        answer = _tokens(output)
        if not answer:
            return 0.0
        return len(answer & _tokens(context)) / len(answer)


class HallucinationEvaluator(Evaluator):
    """Confident assertion combined with weak grounding.

    Encodes the chapter's argument that fluency is not correctness: the
    score rises when an answer is stated absolutely AND is poorly
    supported. A hedged, poorly supported answer scores lower than a
    confident, poorly supported one, which is the ranking you want.
    """

    name = "hallucination"
    lower_is_better = True

    def __init__(self, threshold: float = 0.2, set_version: str = "v1") -> None:
        super().__init__(threshold, set_version)
        self._grounding = GroundednessEvaluator(set_version=set_version)

    def score(self, output: str, *, context: str | None = None, **_: Any) -> float:
        grounded = self._grounding.score(output, context=context)
        confidence = 0.5
        confidence += 0.3 * min(len(_ABSOLUTES.findall(output)), 2) / 2
        confidence -= 0.3 * min(len(_HEDGES.findall(output)), 2) / 2
        confidence = max(0.0, min(1.0, confidence))
        return (1.0 - grounded) * confidence


class RelevanceEvaluator(Evaluator):
    """Overlap between the answer and the question that was asked."""

    name = "relevance"

    def __init__(self, threshold: float = 0.3, set_version: str = "v1") -> None:
        super().__init__(threshold, set_version)

    def score(
        self, output: str, *, context: str | None = None, prompt: str = "", **_: Any
    ) -> float:
        question = _tokens(prompt)
        if not question:
            return 0.0
        return len(_tokens(output) & question) / len(question)
