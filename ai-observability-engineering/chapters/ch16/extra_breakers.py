"""Reference solutions to Exercise 16.3. NOT in the printed listings.

The chapter ships a call-count breaker and a loop-signature breaker.
Exercise 16.3 asks the reader to add two more: one on elapsed wall-clock
time and one on accumulated cost. These are the answers.

Both are wall-clock and money breakers rather than call-count breakers
because the failure they catch is different: a tool that is slow, or a
tool whose individual calls are expensive, can exhaust a budget in three
calls rather than three hundred.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


class BudgetExceeded(RuntimeError):  # noqa: N818 - matches CircuitOpen
    """Raised when a time or cost budget is exhausted."""


@dataclass
class ElapsedTimeBreaker:
    """Opens once a run has been going longer than ``budget_seconds``."""

    budget_seconds: float
    clock: object = field(default=time.monotonic)
    started_at: float = field(init=False)

    def __post_init__(self) -> None:
        if self.budget_seconds <= 0:
            raise ValueError("budget_seconds must be positive")
        self.reset()

    def reset(self) -> None:
        self.started_at = self.clock()  # type: ignore[operator]

    @property
    def elapsed(self) -> float:
        return self.clock() - self.started_at  # type: ignore[operator]

    def check(self) -> None:
        if self.elapsed >= self.budget_seconds:
            raise BudgetExceeded(
                f"run exceeded its {self.budget_seconds}s budget after {self.elapsed:.2f}s"
            )


@dataclass
class CostBreaker:
    """Opens once accumulated spend reaches ``budget_usd``.

    Checked BEFORE the call, using the estimated cost of the call about
    to be made. Checking afterwards means the budget is always exceeded
    by exactly one call, which on an expensive model is the whole point
    of having a budget.
    """

    budget_usd: float
    spent_usd: float = 0.0

    def __post_init__(self) -> None:
        if self.budget_usd <= 0:
            raise ValueError("budget_usd must be positive")

    def reset(self) -> None:
        self.spent_usd = 0.0

    def check(self, next_call_usd: float) -> None:
        if self.spent_usd + next_call_usd > self.budget_usd:
            raise BudgetExceeded(
                f"next call would take spend to "
                f"${self.spent_usd + next_call_usd:.4f}, over the "
                f"${self.budget_usd:.4f} budget"
            )

    def record(self, actual_usd: float) -> None:
        self.spent_usd += actual_usd
