"""Context utilization and memory retrieval quality (Listing 16.2).

Two measurements that agentic systems almost never have.

**Context utilization.** How full was the window on this call, and what
got dropped to make it fit. Truncation counted *by kind* is the useful
form: dropping retrieved documents and dropping tool results are
different failures, and an aggregate "truncations: 412" cannot tell you
which one you have.

**Memory retrieval outcome.** Three states, not two. ``empty`` means the
memory store had nothing to return; ``miss`` means it returned something
and none of it cleared the relevance bar; ``hit`` means it did. Folding
``empty`` into ``miss`` is how a cold-start problem gets diagnosed as a
relevance problem for a quarter.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field

#: A retrieved item at or above this score counts toward a hit.
DEFAULT_RELEVANCE_THRESHOLD = 0.60

OUTCOME_EMPTY = "empty"
OUTCOME_MISS = "miss"
OUTCOME_HIT = "hit"

#: What can be dropped to fit the window, in the order it is dropped.
DROPPABLE_KINDS: tuple[str, ...] = ("retrieval", "tool_results", "history")


@dataclass
class ContextMetrics:
    """Utilization observations and truncation counts by dropped kind."""

    utilizations: list[float] = field(default_factory=list)
    truncations: Counter[str] = field(default_factory=Counter)

    def record_context(
        self,
        *,
        used_tokens: int,
        window_tokens: int,
        dropped: dict[str, int] | None = None,
    ) -> float:
        """Observe one call's utilization and count what was dropped."""
        if window_tokens <= 0:
            raise ValueError("window_tokens must be positive")
        if used_tokens < 0:
            raise ValueError("used_tokens cannot be negative")

        utilization = used_tokens / window_tokens
        self.utilizations.append(utilization)

        for kind, count in (dropped or {}).items():
            if kind not in DROPPABLE_KINDS:
                raise ValueError(f"{kind!r} is not a droppable kind: {DROPPABLE_KINDS}")
            if count:
                self.truncations[kind] += count
        return utilization

    @property
    def mean_utilization(self) -> float:
        if not self.utilizations:
            return 0.0
        return sum(self.utilizations) / len(self.utilizations)

    def truncations_for(self, kind: str) -> int:
        return self.truncations[kind]


@dataclass(frozen=True)
class MemoryItem:
    key: str
    text: str
    embedding: tuple[float, ...]


def cosine_similarity(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    if len(a) != len(b):
        raise ValueError("embeddings must have the same dimension")
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


class LocalVectorStore:
    """A small in-process vector store, so the chapter runs with no service."""

    def __init__(self, items: list[MemoryItem] | None = None) -> None:
        self.items = list(items or [])

    def add(self, item: MemoryItem) -> None:
        self.items.append(item)

    def search(self, query: tuple[float, ...], top_k: int = 3) -> list[tuple[MemoryItem, float]]:
        scored = [(item, cosine_similarity(query, item.embedding)) for item in self.items]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:top_k]


@dataclass
class MemoryMetrics:
    outcomes: Counter[str] = field(default_factory=Counter)

    def record_memory_retrieval(
        self,
        results: list[tuple[MemoryItem, float]],
        *,
        threshold: float = DEFAULT_RELEVANCE_THRESHOLD,
    ) -> str:
        """Classify one retrieval as empty, miss, or hit."""
        if not results:
            outcome = OUTCOME_EMPTY
        elif max(score for _, score in results) >= threshold:
            outcome = OUTCOME_HIT
        else:
            outcome = OUTCOME_MISS

        self.outcomes[outcome] += 1
        return outcome

    def hit_rate(self) -> float:
        """Over retrievals that returned something. An empty store is not a miss."""
        answered = self.outcomes[OUTCOME_HIT] + self.outcomes[OUTCOME_MISS]
        return self.outcomes[OUTCOME_HIT] / answered if answered else 0.0
