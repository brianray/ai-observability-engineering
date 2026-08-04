"""Chapter 11: Regulatory Frameworks and Compliance Mapping."""

from __future__ import annotations

from aiobs import Aiobs, Layer, Pillar, get_tracer

from .registry import example

#: Illustrative crosswalk. Verify against the current text of each
#: framework before relying on it; all three are still moving.
CONTROL_MAP: dict[str, dict[str, str]] = {
    "trace_retention": {
        "nist_ai_rmf": "MEASURE 2.7",
        "eu_ai_act": "Article 12 (record-keeping)",
        "iso_42001": "A.6.2.8",
        "evidence": "span export retained 12 months, immutable store",
    },
    "human_oversight": {
        "nist_ai_rmf": "GOVERN 3.2",
        "eu_ai_act": "Article 14 (human oversight)",
        "iso_42001": "A.9.3",
        "evidence": "aiobs.responsibility.review_outcome present on flagged spans",
    },
    "output_quality_monitoring": {
        "nist_ai_rmf": "MEASURE 2.3",
        "eu_ai_act": "Article 15 (accuracy, robustness)",
        "iso_42001": "A.6.2.6",
        "evidence": "eval.* scores on every production span",
    },
    "incident_reporting": {
        "nist_ai_rmf": "MANAGE 4.3",
        "eu_ai_act": "Article 73 (serious incident reporting)",
        "iso_42001": "A.10.4",
        "evidence": "risk findings routed to the incident queue within 24h",
    },
}


@example(
    chapter=11,
    key="control_crosswalk",
    title="Mapping telemetry to regulatory controls",
    pillar=Pillar.RISK,
    layer=Layer.BUSINESS_AND_OUTCOMES,
    listing="11.4",
)
def control_crosswalk() -> dict:
    """A control you cannot evidence from telemetry is a control you are
    asserting, not operating. Each row names the span attribute that
    proves it."""
    tracer = get_tracer(__name__)
    with tracer.start_as_current_span("compliance.evidence_check") as span:
        span.set_attribute(Aiobs.PILLAR, Pillar.RISK.value)
        span.set_attribute(Aiobs.LAYER, Layer.BUSINESS_AND_OUTCOMES.value)
        span.set_attribute("aiobs.compliance.controls", sorted(CONTROL_MAP))
        span.set_attribute("aiobs.compliance.frameworks", ["nist_ai_rmf", "eu_ai_act", "iso_42001"])

    unevidenced = [k for k, v in CONTROL_MAP.items() if not v.get("evidence")]
    return {
        "controls": len(CONTROL_MAP),
        "crosswalk": CONTROL_MAP,
        "unevidenced_controls": unevidenced,
        "caveat": "framework citations are illustrative; verify current article numbers",
    }
