"""Tag spans with the compliance context an auditor will ask for (Listing 11.1).

The argument this code makes: compliance metadata belongs on the span at
the moment of the decision, not in a spreadsheet reconciled quarterly.
An auditor's question is always "show me this decision, and show me that
you knew what regime it fell under when you made it." Only the first half
is answerable after the fact.

Six attributes, fixed. A registry lookup for an unknown system raises
rather than tagging nothing, because a span that silently carries no
compliance context is indistinguishable from a system nobody registered.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from enum import Enum

from opentelemetry.trace import Span

from aiobs import Aiobs


class RiskCategory(str, Enum):
    """EU AI Act risk tiers, as this book uses them."""

    PROHIBITED = "prohibited"
    HIGH = "high"
    LIMITED = "limited"
    MINIMAL = "minimal"


#: Spans from a high-risk system are retained under a different policy
#: than everything else. The collector reads this attribute to decide
#: what never gets sampled away; see collector-tail-sampling.yaml.
HIGH_RISK_RETENTION_CLASS = "high_risk_decision"


@dataclass(frozen=True)
class ComplianceRecord:
    """What a registered AI system declares about itself."""

    system_id: str
    risk_category: RiskCategory
    frameworks: tuple[str, ...]
    controls: tuple[str, ...]
    lawful_basis: str
    dpia_reference: str | None = None
    #: ``date | None`` needs Python 3.10+ at runtime, or
    #: ``from __future__ import annotations`` (present above) on 3.9.
    #: pyproject declares requires-python >= 3.10, so this is safe.
    last_reviewed: date | None = field(default=None)

    def to_span_attributes(self) -> dict[str, object]:
        """Exactly six ``aiobs.compliance.*`` keys. Not five, not seven.

        Fixed because dashboards and retention rules are built on these
        names; an attribute that appears only sometimes is worse than one
        that never appears, because queries silently under-count.
        """
        return {
            Aiobs.COMPLIANCE_SYSTEM_ID: self.system_id,
            Aiobs.COMPLIANCE_RISK_CATEGORY: self.risk_category.value,
            Aiobs.COMPLIANCE_FRAMEWORKS: list(self.frameworks),
            Aiobs.COMPLIANCE_CONTROLS: list(self.controls),
            Aiobs.COMPLIANCE_LAWFUL_BASIS: self.lawful_basis,
            Aiobs.COMPLIANCE_DPIA_REFERENCE: self.dpia_reference or "none",
        }


class UnknownSystemError(KeyError):
    """Raised when a span names a system that is not in the registry."""


#: The registry. In production this is a service; here it is a dict, and
#: the shape is the point.
REGISTRY: dict[str, ComplianceRecord] = {
    "credit-prescreen": ComplianceRecord(
        system_id="credit-prescreen",
        risk_category=RiskCategory.HIGH,
        frameworks=("eu_ai_act", "nist_ai_rmf", "iso_42001"),
        controls=("trace_retention", "human_oversight", "output_quality_monitoring"),
        lawful_basis="legitimate_interest",
        dpia_reference="DPIA-2026-014",
        last_reviewed=date(2026, 6, 30),
    ),
    "support-summarizer": ComplianceRecord(
        system_id="support-summarizer",
        risk_category=RiskCategory.LIMITED,
        frameworks=("eu_ai_act", "iso_42001"),
        controls=("output_quality_monitoring",),
        lawful_basis="contract",
        dpia_reference=None,
        last_reviewed=date(2026, 5, 12),
    ),
    "doc-classifier": ComplianceRecord(
        system_id="doc-classifier",
        risk_category=RiskCategory.MINIMAL,
        frameworks=("iso_42001",),
        controls=("output_quality_monitoring",),
        lawful_basis="contract",
    ),
}


def lookup(system_id: str, registry: dict[str, ComplianceRecord] | None = None) -> ComplianceRecord:
    """Fetch a record, or raise. Never returns a silent default."""
    source = REGISTRY if registry is None else registry
    try:
        return source[system_id]
    except KeyError as exc:
        raise UnknownSystemError(
            f"{system_id!r} is not in the compliance registry. An unregistered "
            "system must not emit untagged spans: register it or stop it."
        ) from exc


def tag_span_with_compliance(
    span: Span,
    system_id: str,
    registry: dict[str, ComplianceRecord] | None = None,
) -> ComplianceRecord:
    """Tag ``span`` from the registry and set the retention class if high risk."""
    record = lookup(system_id, registry)
    for key, value in record.to_span_attributes().items():
        span.set_attribute(key, value)  # type: ignore[arg-type]

    # Only high-risk systems get the retention class. Tagging everything
    # would make the tail-sampling policy keep 100% of all traffic, which
    # is how a well-meant compliance change becomes a cost incident.
    if record.risk_category is RiskCategory.HIGH:
        span.set_attribute(Aiobs.RETENTION_CLASS, HIGH_RISK_RETENTION_CLASS)

    return record


if __name__ == "__main__":  # pragma: no cover - demonstration record
    import json

    demo = REGISTRY["credit-prescreen"]
    print(json.dumps(asdict(demo), indent=2, default=str))
