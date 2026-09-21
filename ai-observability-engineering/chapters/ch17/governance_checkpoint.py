"""A governance gate inside the graph, not beside it (Listing 17.2).

The pattern: a node that calls langgraph's ``interrupt()`` before the
irreversible step. The run stops, the state is durable in the
checkpointer, and it resumes only when a caller supplies a decision via
``Command(resume=...)``.

Three properties make it a governance control rather than a pause:

1. **The reviewer's role is checked, not just recorded.** A resume from
   the wrong role raises ``PermissionError``. An approval gate that
   accepts any resume value is a speed bump.
2. **The approval joins the responsibility chain.** After approval the
   chain's last hop names the human reviewer as principal, so the
   publish acts on their authority and says so.
3. **It is written to the Chapter 12 audit log**, as an
   ``oversight_action`` event, on approve and on reject alike.

``interrupt()`` re-executes the node from the top on resume, so anything
before the interrupt call runs twice. Keep side effects after it.

**The chain does not propagate back out of a graph node.** A langgraph
node runs in its own copied context, so the ``ContextVar`` mutation from
``delegate()`` is visible inside the node and its callees and is
discarded when the node returns. This is the same boundary as the
thread-pool case in Section 17.3, and it has the same consequence: across
a node boundary the chain has to travel in the graph state, which is also
the thing the checkpointer persists. So this node returns
``responsibility_chain`` in its state update, and callers read it from
there rather than from ``current_chain()`` after the graph returns.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from aiobs import Aiobs, get_tracer
from chapters.ch12 import AuditLogger

from .responsibility_chain import annotate_current_span, current_chain, delegate

#: Roles permitted to clear a publish checkpoint.
DEFAULT_APPROVER_ROLES: frozenset[str] = frozenset({"editor_in_chief", "compliance_officer"})

DECISION_APPROVE = "approve"
DECISION_REJECT = "reject"


@dataclass(frozen=True)
class ApprovalRequest:
    """What the interrupt surfaces to the caller."""

    checkpoint: str
    summary: str
    required_roles: tuple[str, ...]


@dataclass(frozen=True)
class ApprovalResponse:
    """What the caller resumes with."""

    decision: str
    reviewer: str
    reviewer_role: str
    note: str = ""


def make_governance_checkpoint(
    audit: AuditLogger,
    *,
    checkpoint: str = "publish",
    approver_roles: frozenset[str] = DEFAULT_APPROVER_ROLES,
    interrupt_fn: Callable[[Any], Any] | None = None,
):
    """Build the node that gates the publish step.

    ``interrupt_fn`` is injected so the node is testable without a
    langgraph runtime; by default it is ``langgraph.types.interrupt``.
    """

    def _default_interrupt(value: Any) -> Any:
        from langgraph.types import interrupt

        return interrupt(value)

    raise_interrupt = interrupt_fn or _default_interrupt

    def checkpoint_node(state: dict) -> dict:
        request = ApprovalRequest(
            checkpoint=checkpoint,
            summary=str(state.get("draft", ""))[:200],
            required_roles=tuple(sorted(approver_roles)),
        )

        # Everything before this line runs again on resume.
        raw = raise_interrupt(
            {
                "checkpoint": request.checkpoint,
                "summary": request.summary,
                "required_roles": list(request.required_roles),
            }
        )
        response = raw if isinstance(raw, ApprovalResponse) else ApprovalResponse(**raw)

        tracer = get_tracer(__name__)
        with tracer.start_as_current_span(f"checkpoint.{checkpoint}") as span:
            span.set_attribute("aiobs.checkpoint.name", checkpoint)
            span.set_attribute("aiobs.checkpoint.reviewer", response.reviewer)
            span.set_attribute("aiobs.checkpoint.reviewer_role", response.reviewer_role)
            span.set_attribute("aiobs.checkpoint.decision", response.decision)

            if response.reviewer_role not in approver_roles:
                # Raised before anything is recorded as approved: a
                # rejected credential must not leave an approval trail.
                raise PermissionError(
                    f"{response.reviewer_role!r} may not clear the {checkpoint!r} "
                    f"checkpoint; allowed roles are {sorted(approver_roles)}"
                )

            # The human joins the chain. From here the run acts on their
            # authority, and the chain says so.
            delegate(
                f"{checkpoint}_checkpoint",
                delegated_by=response.reviewer,
                action=response.decision,
            )
            annotate_current_span()

            audit.append(
                {
                    "event_type": "oversight_action",
                    "checkpoint": checkpoint,
                    "decision": response.decision,
                    "reviewer": response.reviewer,
                    "reviewer_role": response.reviewer_role,
                    "note": response.note,
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            span.set_attribute(Aiobs.HUMAN_REVIEW_OUTCOME, response.decision)

            # The chain travels in the state, not the ContextVar: a node
            # boundary discards the ContextVar mutation (see the module
            # docstring), and the state is what the checkpointer persists.
            chain = current_chain()

            if response.decision == DECISION_REJECT:
                return {
                    "published": False,
                    "halted_at": checkpoint,
                    "reviewer": response.reviewer,
                    "responsibility_chain": chain,
                }
            return {
                "published": True,
                "halted_at": None,
                "reviewer": response.reviewer,
                "responsibility_chain": chain,
            }

    return checkpoint_node
