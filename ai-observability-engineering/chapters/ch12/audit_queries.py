"""Assembling the dossier an auditor actually asks for (Listing 12.3).

The request is never "give me your logs." It is "show me every decision
this system made about this person between these dates, what it used, who
could see it, and prove none of it changed since." Answering that means
joining the audit chain, the custody ledger, and the verification result
into one artifact.

The stores interface is stubbed against the mock provider, so the whole
assembly runs end to end in CI without an object store.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from .audit_logger import AuditLogger, AuditRecord
from .data_custody import CustodyLedger
from .verify_chain import VerificationResult, verify_chain


@dataclass(frozen=True)
class Dossier:
    subject_ref: str
    period_start: date
    period_end: date
    decisions: list[dict[str, Any]]
    verification: VerificationResult

    @property
    def defensible(self) -> bool:
        """A dossier from an unverifiable chain is not evidence."""
        return self.verification.verified

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject_ref": self.subject_ref,
            "period": [self.period_start.isoformat(), self.period_end.isoformat()],
            "decision_count": len(self.decisions),
            "decisions": self.decisions,
            "chain_verified": self.verification.verified,
            "unverifiable_records": list(self.verification.unverifiable),
            "defensible": self.defensible,
        }


def _in_period(record: AuditRecord, start: date, end: date) -> bool:
    stamp = date.fromisoformat(record.timestamp[:10])
    return start <= stamp <= end


def assemble_dossier(
    logger: AuditLogger,
    custody: CustodyLedger,
    *,
    subject_ref: str,
    period_start: date,
    period_end: date,
) -> Dossier:
    """Join the chain, the custody ledger, and the verification result.

    Verification runs over the WHOLE chain, not just the records in the
    period. A break outside the window still means the records inside it
    cannot be trusted, and a dossier that verified only its own slice
    would hide exactly that.
    """
    all_records = logger.records()
    verification = verify_chain(all_records)

    decisions = []
    for record in all_records:
        if record.payload.get("subject_ref") != subject_ref:
            continue
        if not _in_period(record, period_start, period_end):
            continue
        decision_id = record.payload.get("decision_id", "")
        decisions.append(
            {
                "sequence": record.sequence,
                "timestamp": record.timestamp,
                "decision": record.payload.get("decision"),
                "model": record.payload.get("model"),
                "policy_version": record.payload.get("policy_version"),
                "trace_id": record.payload.get("trace_id"),
                "record_hash": record.record_hash,
                "custody": [e.to_dict() for e in custody.for_decision(decision_id)],
            }
        )

    return Dossier(
        subject_ref=subject_ref,
        period_start=period_start,
        period_end=period_end,
        decisions=decisions,
        verification=verification,
    )
