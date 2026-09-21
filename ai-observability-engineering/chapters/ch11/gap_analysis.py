"""The Table 11.5 gap-analysis template, filled in for the credit-prescreen case.

A gap analysis that lists controls is a document. A gap analysis that
names, for each control, the telemetry that evidences it is a test you
can run. The difference shows up the first time someone asks "is this
still true" nine months later.

``status`` is derived, never typed in: a control with no evidence
attribute is a gap whatever the spreadsheet says.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


class ControlStatus(str, Enum):
    EVIDENCED = "evidenced"       # telemetry proves it on every relevant span
    PARTIAL = "partial"           # evidence exists but does not cover all traffic
    GAP = "gap"                   # asserted, not operated


@dataclass(frozen=True)
class GapRow:
    """One row of Table 11.5."""

    control: str
    eu_ai_act: str
    nist_ai_rmf: str
    iso_42001: str
    #: The span attribute or artifact that proves the control operates.
    #: Empty string means there is nothing to point an auditor at.
    evidence_attribute: str
    owner: str
    target_date: date | None = None
    coverage: float = 0.0

    @property
    def status(self) -> ControlStatus:
        if not self.evidence_attribute:
            return ControlStatus.GAP
        if self.coverage >= 0.99:
            return ControlStatus.EVIDENCED
        return ControlStatus.PARTIAL

    @property
    def is_gap(self) -> bool:
        return self.status is not ControlStatus.EVIDENCED


#: Table 11.5, credit-prescreen example rows.
CREDIT_PRESCREEN_ROWS: tuple[GapRow, ...] = (
    GapRow(
        control="trace_retention",
        eu_ai_act="Article 12 (record-keeping)",
        nist_ai_rmf="MEASURE 2.7",
        iso_42001="A.6.2.8",
        evidence_attribute="aiobs.retention.class",
        owner="Platform SRE",
        target_date=date(2026, 11, 30),
        coverage=1.0,
    ),
    GapRow(
        control="human_oversight",
        eu_ai_act="Article 14 (human oversight)",
        nist_ai_rmf="GOVERN 3.2",
        iso_42001="A.9.3",
        evidence_attribute="aiobs.responsibility.review_outcome",
        owner="Credit Risk Ops",
        target_date=date(2026, 11, 30),
        coverage=1.0,
    ),
    GapRow(
        control="output_quality_monitoring",
        eu_ai_act="Article 15 (accuracy, robustness)",
        nist_ai_rmf="MEASURE 2.3",
        iso_42001="A.6.2.6",
        evidence_attribute="eval.groundedness_score",
        owner="ML Platform",
        target_date=date(2026, 12, 15),
        # Evals run on a sample, not on every decision. That is a real
        # partial, and writing it down as "evidenced" is how a finding
        # arrives during the audit rather than before it.
        coverage=0.25,
    ),
    GapRow(
        control="incident_reporting",
        eu_ai_act="Article 73 (serious incident reporting)",
        nist_ai_rmf="MANAGE 4.3",
        iso_42001="A.10.4",
        evidence_attribute="aiobs.risk.owasp_id",
        owner="Security Ops",
        target_date=date(2026, 12, 15),
        coverage=1.0,
    ),
    GapRow(
        control="bias_monitoring",
        eu_ai_act="Article 10 (data governance)",
        nist_ai_rmf="MEASURE 2.11",
        iso_42001="A.6.2.4",
        # Chapter 13's fairness metrics are not wired to this system yet.
        evidence_attribute="",
        owner="Responsible AI",
        target_date=date(2027, 3, 31),
        coverage=0.0,
    ),
)


def gaps(rows: tuple[GapRow, ...] = CREDIT_PRESCREEN_ROWS) -> list[GapRow]:
    """Every row that is not fully evidenced."""
    return [row for row in rows if row.is_gap]


def summary(rows: tuple[GapRow, ...] = CREDIT_PRESCREEN_ROWS) -> dict:
    return {
        "controls": len(rows),
        "evidenced": sum(1 for r in rows if r.status is ControlStatus.EVIDENCED),
        "partial": sum(1 for r in rows if r.status is ControlStatus.PARTIAL),
        "gap": sum(1 for r in rows if r.status is ControlStatus.GAP),
        "open_controls": [r.control for r in gaps(rows)],
    }
