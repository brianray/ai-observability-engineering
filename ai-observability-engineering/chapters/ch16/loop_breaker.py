"""Catching the loop that is not an exact repeat (Listing 16.3).

An agent stuck in a loop rarely issues byte-identical calls. It rephrases:
"refund policy for orders" then "orders refund policy" then "policy on
refunds for orders". An exact-match detector sees three distinct queries
and lets the loop run.

``text_similarity`` is a **normalized token-set ratio**: lowercase, split
on non-word characters, drop duplicates, and divide the intersection by
the union (Jaccard). It is chosen over an edit-distance measure because
it is word-order invariant, which is exactly the permutation the failure
mode produces, and it is O(n) rather than O(n*m) so it can run on every
call without becoming its own cost problem. It will not catch a loop that
paraphrases with different vocabulary; that is a known limit, and the
call-count breaker in ``observable_tool.py`` is the backstop.
"""

from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field

#: Two calls are "the same question" at or above this similarity.
DEFAULT_SIMILARITY_THRESHOLD = 0.75

#: How many recent calls to keep. The breaker opens when the window is
#: full and every pair in it is similar.
DEFAULT_WINDOW = 4

_TOKEN = re.compile(r"\w+")


def text_similarity(left: str, right: str) -> float:
    """Normalized token-set (Jaccard) ratio in [0, 1]."""
    a = set(_TOKEN.findall(left.lower()))
    b = set(_TOKEN.findall(right.lower()))
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


@dataclass
class LoopSignatureBreaker:
    """Opens when a full window of recent calls are all near-duplicates."""

    window: int = DEFAULT_WINDOW
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD
    recent: deque[str] = field(default_factory=deque)
    opened: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if self.window < 2:
            raise ValueError("a window smaller than 2 cannot contain a repeat")
        self.recent = deque(maxlen=self.window)

    def reset(self) -> None:
        self.recent.clear()
        self.opened = False

    def observe(self, call_text: str) -> bool:
        """Record a call. Returns True when the breaker is open."""
        self.recent.append(call_text)
        if len(self.recent) < self.window:
            return self.opened

        # Every pair, not just consecutive ones: a loop that alternates
        # between two phrasings has similar pairs at distance two, and a
        # consecutive-only check would miss an A-B-A-B oscillation.
        items = list(self.recent)
        self.opened = all(
            text_similarity(items[i], items[j]) >= self.threshold
            for i in range(len(items))
            for j in range(i + 1, len(items))
        )
        return self.opened
