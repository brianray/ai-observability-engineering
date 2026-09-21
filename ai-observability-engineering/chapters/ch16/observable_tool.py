"""Wrapping a tool so its failures are visible (Listing 16.1).

A tool call is the point where an agent touches the world, and it is
where agent cost and agent damage both originate. Three things this
wrapper insists on:

**A call budget.** ``max_calls`` is a circuit breaker, not a rate limit.
Once it trips the tool stops being callable until someone resets it,
because the failure it exists to stop is a loop that would otherwise run
until the bill arrives.

**Bounded previews.** Arguments and results are previewed, truncated, and
passed through the tool's own redactor. A tool that reads customer
records must not put them on spans, and the wrapper cannot know which
fields matter, so redaction is the tool's responsibility and the byte cap
is the wrapper's.

**A stable argument hash.** ``args_hash`` is computed over canonically
ordered arguments, so the same call made twice hashes the same however
the kwargs dict was built. That is what makes loop detection possible.

Elapsed-time and cost breakers are **Exercise 16.3**; the reference
implementations are in ``extra_breakers.py`` and are deliberately not in
the printed listing.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from aiobs import Operation, get_tracer
from aiobs.semconv import GenAI

#: Argument and result previews are truncated to this many bytes.
PREVIEW_BYTES = 256

OUTCOME_OK = "ok"
OUTCOME_ERROR = "error"
OUTCOME_BREAKER_OPEN = "breaker_open"


class CircuitOpen(RuntimeError):  # noqa: N818 - the name Listing 16.1 prints
    """Raised when a tool's call budget is exhausted."""


Redactor = Callable[[str], str]


def identity_redactor(text: str) -> str:
    return text


def _canonical(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    except TypeError:
        return repr(value)


def args_hash(args: tuple, kwargs: dict) -> str:
    """Stable across kwargs insertion order."""
    return hashlib.sha256(
        _canonical({"args": list(args), "kwargs": kwargs}).encode("utf-8")
    ).hexdigest()


def preview(value: Any, redactor: Redactor = identity_redactor) -> str:
    """Redact first, then truncate.

    Order matters: truncating first can slice a redaction pattern in half
    and leave the tail of a card number on the span.
    """
    text = redactor(_canonical(value))
    encoded = text.encode("utf-8")[:PREVIEW_BYTES]
    return encoded.decode("utf-8", errors="ignore")


@dataclass
class ToolCounter:
    counts: Counter[tuple[str, str]] = field(default_factory=Counter)

    def increment(self, tool: str, outcome: str) -> None:
        self.counts[(tool, outcome)] += 1

    def get(self, tool: str, outcome: str) -> int:
        return self.counts[(tool, outcome)]


@dataclass
class ObservableTool:
    """A callable tool with a call budget, previews, and span attributes."""

    name: str
    func: Callable[..., Any]
    counter: ToolCounter
    max_calls: int = 10
    redactor: Redactor = identity_redactor
    calls: int = field(default=0, init=False)

    def reset(self) -> None:
        """Close the breaker again. Deliberately explicit."""
        self.calls = 0

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        tracer = get_tracer(__name__)
        with tracer.start_as_current_span(f"execute_tool {self.name}") as span:
            span.set_attribute(GenAI.OPERATION_NAME, Operation.EXECUTE_TOOL)
            span.set_attribute(GenAI.TOOL_NAME, self.name)
            span.set_attribute(GenAI.PROVIDER_NAME, "internal")
            span.set_attribute("aiobs.tool.args_hash", args_hash(args, kwargs))
            span.set_attribute("aiobs.tool.args_preview", preview({"args": args, "kwargs": kwargs}, self.redactor))
            span.set_attribute("aiobs.tool.calls", self.calls)

            if self.calls >= self.max_calls:
                span.set_attribute("aiobs.tool.outcome", OUTCOME_BREAKER_OPEN)
                self.counter.increment(self.name, OUTCOME_BREAKER_OPEN)
                raise CircuitOpen(
                    f"{self.name} exhausted its budget of {self.max_calls} calls"
                )

            self.calls += 1
            try:
                result = self.func(*args, **kwargs)
            except Exception:
                span.set_attribute("aiobs.tool.outcome", OUTCOME_ERROR)
                self.counter.increment(self.name, OUTCOME_ERROR)
                raise

            span.set_attribute("aiobs.tool.result_preview", preview(result, self.redactor))
            span.set_attribute("aiobs.tool.outcome", OUTCOME_OK)
            self.counter.increment(self.name, OUTCOME_OK)
            return result
