"""Carrying "on whose authority" across agent handoffs (Listing 17.1).

When agent C acts, someone has to be able to answer on whose authority.
That answer is only cheap to produce if it was recorded at the time; a
reconstruction during an incident is a reconstruction, and it is the
thing nobody trusts.

The chain lives in a ``ContextVar``, which is the right primitive for
task-local state in async code and is the reason two concurrent runs do
not interleave. It is also the reason the chain does **not** cross a
thread-pool boundary on its own: ``run_in_executor`` starts the callable
on a worker thread with a fresh context. Chapter 5's attach/detach
pattern (Listing 5.4) is what carries it over, and the test suite keeps
a negative case showing the chain empty on the pool thread when it is
not used, because "it worked on my machine" here means "I never tried it
concurrently".
"""

from __future__ import annotations

import json
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from typing import Any

from opentelemetry import trace

from aiobs import Aiobs

#: Task-local. Each asyncio task and each new thread gets its own view.
_chain: ContextVar[tuple[Hop, ...]] = ContextVar("responsibility_chain", default=())


class ChainNotStartedError(RuntimeError):
    """Raised when ``delegate`` is called outside ``start_chain``."""


@dataclass(frozen=True)
class Hop:
    """One delegation step."""

    actor: str
    principal: str
    action: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def current_chain() -> tuple[Hop, ...]:
    return _chain.get()


def current_principal() -> str | None:
    chain = _chain.get()
    return chain[-1].principal if chain else None


class _ChainScope:
    """Context manager restoring the previous chain on exit."""

    def __init__(self, hops: tuple[Hop, ...]) -> None:
        self._hops = hops
        self._token: Any = None

    def __enter__(self) -> tuple[Hop, ...]:
        self._token = _chain.set(self._hops)
        return self._hops

    def __exit__(self, *exc: Any) -> None:
        _chain.reset(self._token)


def start_chain(actor: str, principal: str, action: str = "start") -> _ChainScope:
    """Open a chain rooted at a named human principal.

        with start_chain("intake_agent", "human_operator"):
            delegate("planner_agent", action="plan")
    """
    return _ChainScope((Hop(actor=actor, principal=principal, action=action),))


def delegate(actor: str, *, delegated_by: str | None = None, action: str = "act") -> Hop:
    """Add a hop. Raises outside ``start_chain``.

    ``delegated_by`` defaults to the previous hop's principal, so
    authority flows forward rather than being re-asserted at each step.
    An agent cannot grant itself an authority the chain never gave it.
    """
    chain = _chain.get()
    if not chain:
        raise ChainNotStartedError(
            "delegate() outside start_chain(): a hop with no chain behind it has "
            "no principal, which is the condition this module exists to prevent"
        )

    hop = Hop(actor=actor, principal=delegated_by or chain[-1].principal, action=action)
    _chain.set((*chain, hop))
    return hop


def chain_as_json(chain: tuple[Hop, ...] | None = None) -> str:
    return json.dumps([hop.to_dict() for hop in (chain if chain is not None else _chain.get())])


def annotate_current_span() -> str:
    """Serialize the chain onto the current span. Returns the JSON written."""
    payload = chain_as_json()
    span = trace.get_current_span()
    span.set_attribute(Aiobs.RESPONSIBILITY_CHAIN, payload)
    principal = current_principal()
    if principal:
        span.set_attribute(Aiobs.RESPONSIBILITY_PRINCIPAL, principal)
    return payload


def carry_context():
    """The Chapter 5 attach/detach handle, for crossing a thread boundary.

    Returns a snapshot to be applied on the worker thread::

        snapshot = carry_context()
        await loop.run_in_executor(pool, lambda: _with(snapshot, work))

    Without this the pool thread sees an empty chain, which is the
    negative test in the suite.
    """
    return _chain.get()


def apply_context(snapshot: tuple[Hop, ...]):
    """Attach a carried chain on this thread. Returns a reset token."""
    return _chain.set(snapshot)


def release_context(token: Any) -> None:
    _chain.reset(token)
