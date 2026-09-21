"""One structured logging path for the whole book.

Chapter 3 introduces logs as one of the four signals and argues that a
log line is only useful when it is an event with fields, correlated to
the trace that produced it. Chapter 10 then emits security events from a
detector. Those two chapters must not grow separate loggers: a reader who
wires up Chapter 3's logging and then copies Chapter 10's detector should
get one stream, not two.

So the logger lives here, and both chapters import it.

Two properties matter more than the formatting:

1. **Fields, not sentences.** ``emit("guardrail.blocked", action="block")``
   is queryable. ``"blocked a prompt"`` is not.
2. **No payload, ever.** ``emit`` refuses values that look like free
   text over ``MAX_FIELD_CHARS``, because the reliable way to keep the
   attacker's string out of the log pipeline is to make putting it there
   fail loudly rather than depend on every call site remembering.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from opentelemetry import trace

#: Field values longer than this are rejected. A detector has no reason
#: to log a 2,000 character prompt; if it wants to, that is the bug.
MAX_FIELD_CHARS: int = 200

_RESERVED = ("event", "trace_id", "span_id")


class PayloadInLogError(ValueError):
    """Raised when a field value is long enough to be a payload."""


@dataclass(frozen=True)
class LogRecord:
    """One structured event. ``fields`` never contains raw model text."""

    event: str
    level: str
    fields: dict[str, Any] = field(default_factory=dict)
    trace_id: str | None = None
    span_id: str | None = None

    def to_json(self) -> str:
        payload = {"event": self.event, "level": self.level, **self.fields}
        if self.trace_id:
            payload["trace_id"] = self.trace_id
            payload["span_id"] = self.span_id
        return json.dumps(payload, sort_keys=True)


#: Set while ``capture_logs`` is active. Tests assert on records rather
#: than scraping formatted output.
_buffer: list[LogRecord] | None = None


@contextmanager
def capture_logs() -> Iterator[list[LogRecord]]:
    """Collect every record emitted in the block.

    The test-facing counterpart of ``aiobs.capture`` for spans.
    """
    global _buffer
    previous = _buffer
    records: list[LogRecord] = []
    _buffer = records
    try:
        yield records
    finally:
        _buffer = previous


def _current_ids() -> tuple[str | None, str | None]:
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if not ctx.is_valid:
        return None, None
    return format(ctx.trace_id, "032x"), format(ctx.span_id, "016x")


class StructuredLogger:
    """Emits ``LogRecord``s. One per chapter module, named after it."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._stdlib = logging.getLogger(name)

    def emit(self, event: str, *, level: str = "info", **fields: Any) -> LogRecord:
        """Emit one event. Returns the record so callers can assert on it."""
        for reserved in _RESERVED:
            if reserved in fields:
                raise ValueError(f"{reserved!r} is set by the logger, not the caller")
        for key, value in fields.items():
            if isinstance(value, str) and len(value) > MAX_FIELD_CHARS:
                raise PayloadInLogError(
                    f"field {key!r} is {len(value)} chars, over the {MAX_FIELD_CHARS} "
                    "limit. Log a reference to the payload, not the payload."
                )

        trace_id, span_id = _current_ids()
        record = LogRecord(
            event=event, level=level, fields=dict(fields), trace_id=trace_id, span_id=span_id
        )
        if _buffer is not None:
            _buffer.append(record)
        self._stdlib.log(getattr(logging, level.upper(), logging.INFO), record.to_json())
        return record

    def warning(self, event: str, **fields: Any) -> LogRecord:
        return self.emit(event, level="warning", **fields)


def get_logger(name: str) -> StructuredLogger:
    """The one logger factory. Chapters 3 and 10 both call this."""
    return StructuredLogger(name)
