"""The decision record an incident review actually needs (Listing 17.3).

Table 17.3's fields, assembled from the telemetry the previous chapters
emit rather than written by hand afterwards. Every field has a source,
and ``missing_fields`` names anything that could not be filled, because
a record with silent gaps reads as complete.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import datetime
from typing import Any

from .responsibility_chain import Hop


@dataclass
class DecisionRecord:
    """Table 17.3."""

    decision_id: str
    trace_id: str
    occurred_at: datetime
    system_id: str
    #: What the system did.
    action: str
    outcome: str
    #: Who is answerable. The last hop's principal, not the last actor.
    accountable_principal: str
    responsibility_chain: tuple[Hop, ...]
    #: Which model and policy produced it.
    model: str
    policy_version: str
    #: Human oversight.
    reviewer: str | None
    review_decision: str | None
    #: Evidence.
    audit_record_hash: str
    inputs_ref: str
    #: Regulatory context (Chapter 11).
    risk_category: str
    frameworks: tuple[str, ...] = field(default_factory=tuple)

    @property
    def missing_fields(self) -> tuple[str, ...]:
        """Fields that are empty. Optional review fields are excluded."""
        optional = {"reviewer", "review_decision"}
        missing = []
        for f in fields(self):
            if f.name in optional:
                continue
            value = getattr(self, f.name)
            if value in (None, "", (), []):
                missing.append(f.name)
        return tuple(missing)

    @property
    def complete(self) -> bool:
        return not self.missing_fields

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "trace_id": self.trace_id,
            "occurred_at": self.occurred_at.isoformat(),
            "system_id": self.system_id,
            "action": self.action,
            "outcome": self.outcome,
            "accountable_principal": self.accountable_principal,
            "responsibility_chain": [hop.to_dict() for hop in self.responsibility_chain],
            "model": self.model,
            "policy_version": self.policy_version,
            "reviewer": self.reviewer,
            "review_decision": self.review_decision,
            "audit_record_hash": self.audit_record_hash,
            "inputs_ref": self.inputs_ref,
            "risk_category": self.risk_category,
            "frameworks": list(self.frameworks),
        }


def assemble_decision_record(
    *,
    decision_id: str,
    trace_id: str,
    occurred_at: datetime,
    system_id: str,
    action: str,
    outcome: str,
    chain: tuple[Hop, ...],
    model: str,
    policy_version: str,
    audit_record_hash: str,
    inputs_ref: str,
    risk_category: str,
    frameworks: tuple[str, ...],
    reviewer: str | None = None,
    review_decision: str | None = None,
) -> DecisionRecord:
    """Build the record, deriving the accountable principal from the chain."""
    if not chain:
        raise ValueError(
            "a decision record with no responsibility chain has no accountable "
            "principal, which is the one field the record exists for"
        )

    return DecisionRecord(
        decision_id=decision_id,
        trace_id=trace_id,
        occurred_at=occurred_at,
        system_id=system_id,
        action=action,
        outcome=outcome,
        accountable_principal=chain[-1].principal,
        responsibility_chain=chain,
        model=model,
        policy_version=policy_version,
        reviewer=reviewer,
        review_decision=review_decision,
        audit_record_hash=audit_record_hash,
        inputs_ref=inputs_ref,
        risk_category=risk_category,
        frameworks=frameworks,
    )
