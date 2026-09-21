"""Unit tests: Chapter 11 compliance companion."""

from __future__ import annotations

import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

import pytest
import yaml

from aiobs import Aiobs, capture, get_tracer
from chapters.ch11 import (
    HIGH_RISK_RETENTION_CLASS,
    REGISTRY,
    ComplianceRecord,
    ControlStatus,
    RiskCategory,
    UnknownSystemError,
    gaps,
    summary,
    tag_span_with_compliance,
)
from chapters.ch11.gap_analysis import CREDIT_PRESCREEN_ROWS

FRAGMENT = Path("chapters/ch11/collector-tail-sampling.yaml")
CH05_COLLECTOR = Path("config/otel-collector.yaml")

COMPLIANCE_KEYS = {
    Aiobs.COMPLIANCE_SYSTEM_ID,
    Aiobs.COMPLIANCE_RISK_CATEGORY,
    Aiobs.COMPLIANCE_FRAMEWORKS,
    Aiobs.COMPLIANCE_CONTROLS,
    Aiobs.COMPLIANCE_LAWFUL_BASIS,
    Aiobs.COMPLIANCE_DPIA_REFERENCE,
}


def _tag(system_id: str):
    # get_tracer must be called inside capture(): capture() reconfigures
    # the provider, so a tracer fetched beforehand writes to the previous
    # exporter and the captured list comes back empty.
    with capture() as spans:
        tracer = get_tracer(__name__)
        with tracer.start_as_current_span("decision") as span:
            tag_span_with_compliance(span, system_id)
    return dict(spans[0].attributes or {})


def test_to_span_attributes_emits_exactly_six_compliance_keys():
    attrs = REGISTRY["credit-prescreen"].to_span_attributes()
    assert set(attrs) == COMPLIANCE_KEYS
    assert len(attrs) == 6


def test_optional_dpia_reference_is_still_emitted_as_a_value():
    """An absent attribute and 'no DPIA' must not look the same in a query."""
    attrs = REGISTRY["support-summarizer"].to_span_attributes()
    assert set(attrs) == COMPLIANCE_KEYS
    assert attrs[Aiobs.COMPLIANCE_DPIA_REFERENCE] == "none"


def test_retention_class_is_set_only_for_high_risk():
    high = _tag("credit-prescreen")
    assert high[Aiobs.RETENTION_CLASS] == HIGH_RISK_RETENTION_CLASS

    for limited in ("support-summarizer", "doc-classifier"):
        attrs = _tag(limited)
        assert Aiobs.RETENTION_CLASS not in attrs, (
            "tagging non-high-risk traffic with the retention class makes the "
            "tail-sampling policy keep 100% of everything"
        )


def test_unknown_system_raises_rather_than_tagging_nothing():
    with capture():
        tracer = get_tracer(__name__)
        with tracer.start_as_current_span("decision") as span:
            with pytest.raises(UnknownSystemError):
                tag_span_with_compliance(span, "not-registered")


def test_demonstration_record_round_trips_through_asdict():
    record = REGISTRY["credit-prescreen"]
    payload = asdict(record)
    restored = ComplianceRecord(
        system_id=payload["system_id"],
        risk_category=RiskCategory(payload["risk_category"]),
        frameworks=tuple(payload["frameworks"]),
        controls=tuple(payload["controls"]),
        lawful_basis=payload["lawful_basis"],
        dpia_reference=payload["dpia_reference"],
        last_reviewed=payload["last_reviewed"],
    )
    assert restored == record


def test_date_or_none_annotation_holds_on_the_pinned_python():
    """`date | None` is evaluated at runtime by dataclasses on 3.10+."""
    assert sys.version_info >= (3, 10)
    assert REGISTRY["doc-classifier"].last_reviewed is None
    assert REGISTRY["credit-prescreen"].last_reviewed == date(2026, 6, 30)


# --- collector fragment ---


def test_tail_sampling_policy_keeps_all_high_risk_decision_spans():
    doc = yaml.safe_load(FRAGMENT.read_text(encoding="utf-8"))
    policies = doc["processors"]["tail_sampling/compliance"]["policies"]
    by_name = {p["name"]: p for p in policies}

    keep = by_name["keep-all-high-risk-decisions"]
    assert keep["type"] == "string_attribute"
    assert keep["string_attribute"]["key"] == Aiobs.RETENTION_CLASS
    assert HIGH_RISK_RETENTION_CLASS in keep["string_attribute"]["values"]
    assert keep["string_attribute"].get("invert_match") is False


def test_fragment_replaces_rather_than_stacks_the_probabilistic_sampler():
    """Running both drops high-risk spans before tail sampling sees them."""
    doc = yaml.safe_load(FRAGMENT.read_text(encoding="utf-8"))
    processors = doc["service"]["pipelines"]["traces/sampled"]["processors"]
    assert "tail_sampling/compliance" in processors
    assert not any(p.startswith("probabilistic_sampler") for p in processors)


def test_fragment_stays_consistent_with_the_chapter_5_collector():
    """Cross-reference: same pipeline name, same redaction, same fallback rate."""
    fragment = yaml.safe_load(FRAGMENT.read_text(encoding="utf-8"))
    ch05 = yaml.safe_load(CH05_COLLECTOR.read_text(encoding="utf-8"))

    assert "traces/sampled" in ch05["service"]["pipelines"]
    # Redaction must survive the swap, or the fragment quietly removes it.
    assert "attributes/redact" in fragment["service"]["pipelines"]["traces/sampled"]["processors"]

    ch05_rate = ch05["processors"]["probabilistic_sampler/traces"]["sampling_percentage"]
    policies = {p["name"]: p for p in fragment["processors"]["tail_sampling/compliance"]["policies"]}
    fallback = policies["sample-the-rest"]["probabilistic"]["sampling_percentage"]
    assert fallback == ch05_rate, (
        "the fallback rate must match Chapter 5's, or the two chapters describe "
        "two different sampling stories"
    )


# --- gap analysis ---


def test_status_is_derived_from_evidence_not_asserted():
    row = next(r for r in CREDIT_PRESCREEN_ROWS if r.control == "bias_monitoring")
    assert row.evidence_attribute == ""
    assert row.status is ControlStatus.GAP


def test_partial_coverage_is_not_reported_as_evidenced():
    row = next(r for r in CREDIT_PRESCREEN_ROWS if r.control == "output_quality_monitoring")
    assert 0.0 < row.coverage < 0.99
    assert row.status is ControlStatus.PARTIAL
    assert row.is_gap


def test_credit_prescreen_rows_are_filled_in():
    assert len(CREDIT_PRESCREEN_ROWS) >= 5
    for row in CREDIT_PRESCREEN_ROWS:
        assert row.eu_ai_act and row.nist_ai_rmf and row.iso_42001
        assert row.owner
    assert summary()["controls"] == len(CREDIT_PRESCREEN_ROWS)
    assert {r.control for r in gaps()} == {"output_quality_monitoring", "bias_monitoring"}


# --- EU AI Act timeline ---


def test_digital_omnibus_defers_only_the_high_risk_obligations():
    from chapters.ch11.eu_ai_act_timeline import (
        UNAFFECTED_BY_DEFERRAL,
        deferred_obligations,
    )

    deferred = {o.key for o in deferred_obligations()}
    assert deferred == {"high_risk_annex_iii", "high_risk_annex_i"}
    assert not deferred & set(UNAFFECTED_BY_DEFERRAL)


def test_annex_iii_moves_from_august_2026_to_december_2027():
    from chapters.ch11.eu_ai_act_timeline import by_key

    annex_iii = by_key("high_risk_annex_iii")
    assert annex_iii.original_date == date(2026, 8, 2)
    assert annex_iii.applies_from == date(2027, 12, 2)

    annex_i = by_key("high_risk_annex_i")
    assert annex_i.applies_from == date(2028, 8, 2)


def test_transparency_and_gpai_duties_are_not_deferred():
    from chapters.ch11.eu_ai_act_timeline import by_key

    assert by_key("transparency_article_50").applies_from == date(2026, 8, 2)
    assert by_key("transparency_article_50").deferred is False
    assert by_key("gpai_provider_obligations").applies_from == date(2025, 8, 2)
    assert by_key("prohibited_practices").applies_from == date(2025, 2, 2)


def test_omnibus_entered_into_force_three_days_after_publication():
    from chapters.ch11.eu_ai_act_timeline import (
        DIGITAL_OMNIBUS_IN_FORCE,
        DIGITAL_OMNIBUS_PUBLISHED,
    )

    assert date(2026, 7, 24) == DIGITAL_OMNIBUS_PUBLISHED
    assert date(2026, 7, 27) == DIGITAL_OMNIBUS_IN_FORCE
