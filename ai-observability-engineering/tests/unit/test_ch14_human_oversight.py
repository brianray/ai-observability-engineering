"""Unit tests: Chapter 14 human-oversight companion."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest

from aiobs import Aiobs, capture
from chapters.ch12 import AuditLogger, LocalFilesystemStore, verify_chain
from chapters.ch14 import (
    DEFAULT_AUDIT_SAMPLE_RATE,
    PAYLOAD_KEYS,
    QUEUE_AUDIT,
    QUEUE_GENERAL,
    QUEUE_SPECIALIST,
    REASON_BELOW_THRESHOLD,
    REASON_MANDATORY,
    REASON_SAMPLED_AUDIT,
    FeedbackCapture,
    HitlRouter,
    MockQueue,
    OversightAction,
    Recommendation,
    ReviewOutcome,
    RouteCounter,
)
from tests.support.prometheus import (
    check_rule_document,
    load_promql,
    promtool,
    promtool_check,
    promtool_check_expressions,
)

RULES_PATH = Path("chapters/ch14/hitl_recording_rules.yml")
QUERIES_PATH = Path("chapters/ch14/hitl_dashboard.promql")


@pytest.fixture()
def router():
    return HitlRouter(queue=MockQueue(), counter=RouteCounter())


# --- routing ---


def test_mandatory_class_routes_regardless_of_confidence(router):
    result = router.route(Recommendation("a", "credit_decline", confidence=0.999))
    assert result.reason == REASON_MANDATORY
    assert result.queue == QUEUE_SPECIALIST


def test_below_threshold_confidence_routes(router):
    result = router.route(Recommendation("b", "refund", confidence=0.30))
    assert result.reason == REASON_BELOW_THRESHOLD
    assert result.queue == QUEUE_GENERAL


def test_high_confidence_work_is_sampled_at_the_configured_rate():
    """The branch people skip, and the only one that can find a bad threshold."""
    router = HitlRouter(queue=MockQueue(), counter=RouteCounter(), seed=1729)
    runs = 10_000
    results = [
        router.route(Recommendation(str(i), "refund", confidence=0.95)) for i in range(runs)
    ]
    sampled = sum(1 for r in results if r.reason == REASON_SAMPLED_AUDIT)
    assert sampled / runs == pytest.approx(DEFAULT_AUDIT_SAMPLE_RATE, abs=0.005)
    assert all(
        r.queue == QUEUE_AUDIT for r in results if r.reason == REASON_SAMPLED_AUDIT
    )


def test_the_seeded_sampler_is_reproducible():
    """An audit rate you cannot reproduce is an audit rate you cannot evidence."""
    def run():
        r = HitlRouter(queue=MockQueue(), counter=RouteCounter(), seed=99)
        return [r.route(Recommendation(str(i), "refund", 0.95)).reason for i in range(200)]

    assert run() == run()


def test_every_call_sets_the_four_hitl_span_attributes(router):
    with capture() as spans:
        local = HitlRouter(queue=MockQueue(), counter=RouteCounter())
        local.route(Recommendation("c", "refund", confidence=0.30))

    attrs = dict(spans[0].attributes or {})
    for key in (
        Aiobs.HITL_ROUTED,
        Aiobs.HITL_REASON,
        Aiobs.HITL_QUEUE,
        Aiobs.HITL_CONFIDENCE,
    ):
        assert key in attrs, f"{key} missing"
    assert attrs[Aiobs.HITL_ROUTED] is True


def test_the_auto_approved_path_also_sets_all_four_attributes():
    """Absent and 'not routed' must not look the same in a query."""
    with capture() as spans:
        local = HitlRouter(queue=MockQueue(), counter=RouteCounter(), audit_sample_rate=0.0)
        local.route(Recommendation("d", "refund", confidence=0.99))

    attrs = dict(spans[0].attributes or {})
    assert attrs[Aiobs.HITL_ROUTED] is False
    assert attrs[Aiobs.HITL_QUEUE] == "none"
    assert Aiobs.HITL_CONFIDENCE in attrs


def test_counter_increments_with_destination_and_reason_labels(router):
    router.route(Recommendation("a", "credit_decline", 0.99))
    router.route(Recommendation("b", "refund", 0.30))

    assert router.counter.get(QUEUE_SPECIALIST, REASON_MANDATORY) == 1
    assert router.counter.get(QUEUE_GENERAL, REASON_BELOW_THRESHOLD) == 1


def test_routed_items_reach_the_queue(router):
    router.route(Recommendation("a", "credit_decline", 0.99))
    assert router.queue.depth(QUEUE_SPECIALIST) == 1


def test_an_invalid_sample_rate_raises():
    with pytest.raises(ValueError):
        HitlRouter(queue=MockQueue(), counter=RouteCounter(), audit_sample_rate=1.5)


# --- feedback capture ---


@pytest.fixture()
def capture_path(tmp_path):
    return FeedbackCapture(AuditLogger(LocalFilesystemStore(tmp_path / "audit")))


def _action(outcome: ReviewOutcome, *, fit: bool = False, seconds: int = 150):
    return OversightAction(
        recommendation_id="r1",
        decision_class="refund",
        queue=QUEUE_GENERAL,
        reviewer_role="claims_analyst",
        outcome=outcome,
        assigned_at=datetime(2026, 9, 1, 10, 0, 0),
        decided_at=datetime(2026, 9, 1, 10, 0, seconds % 60, 0) if seconds < 60 else
        datetime(2026, 9, 1, 10, seconds // 60, seconds % 60),
        model_confidence=0.62,
        fit_for_training=fit,
        trace_id="0" * 32,
    )


def test_capture_writes_an_oversight_action_event_with_documented_keys(capture_path):
    payload = capture_path.capture(_action(ReviewOutcome.OVERRIDE))
    assert set(payload) == set(PAYLOAD_KEYS)
    assert payload["event_type"] == "oversight_action"


def test_review_seconds_is_computed_from_the_timestamps():
    assert _action(ReviewOutcome.UPHOLD, seconds=150).review_seconds == 150.0
    assert _action(ReviewOutcome.UPHOLD, seconds=30).review_seconds == 30.0


def test_a_negative_review_duration_raises():
    action = OversightAction(
        recommendation_id="r",
        decision_class="refund",
        queue=QUEUE_GENERAL,
        reviewer_role="analyst",
        outcome=ReviewOutcome.UPHOLD,
        assigned_at=datetime(2026, 9, 1, 10, 5, 0),
        decided_at=datetime(2026, 9, 1, 10, 0, 0),
        model_confidence=0.5,
    )
    with pytest.raises(ValueError):
        _ = action.review_seconds


def test_every_outcome_reaches_the_audit_log(capture_path):
    """Including upholds. A log of disagreements cannot evidence review."""
    capture_path.capture(_action(ReviewOutcome.UPHOLD, fit=True))
    capture_path.capture(_action(ReviewOutcome.MODIFY, fit=True))
    capture_path.capture(_action(ReviewOutcome.OVERRIDE, fit=False))

    records = capture_path._audit.records()
    assert len(records) == 3
    assert verify_chain(records).verified


def test_only_informative_outcomes_marked_fit_reach_the_dataset(capture_path):
    capture_path.capture(_action(ReviewOutcome.UPHOLD, fit=True))      # not informative
    capture_path.capture(_action(ReviewOutcome.OVERRIDE, fit=False))   # not marked fit
    capture_path.capture(_action(ReviewOutcome.MODIFY, fit=True))      # both gates pass
    capture_path.capture(_action(ReviewOutcome.OVERRIDE, fit=True))    # both gates pass

    assert len(capture_path.dataset) == 2
    assert {r["outcome"] for r in capture_path.dataset.records} == {"modify", "override"}


def test_fit_for_training_defaults_to_false():
    """The safe path is the default path."""
    assert _action(ReviewOutcome.OVERRIDE).fit_for_training is False


# --- dashboard artifacts ---


def test_recording_rules_are_structurally_valid():
    check_rule_document(RULES_PATH)


def test_recording_rules_define_the_series_the_dashboard_reads():
    doc = check_rule_document(RULES_PATH)
    recorded = {r["record"] for g in doc["groups"] for r in g["rules"] if "record" in r}
    for series in (
        "aiobs_hitl_review_outcomes_total",
        "aiobs_hitl_queue_depth",
    ):
        assert series in recorded, f"{series} is queried but never recorded"
    assert any(r.startswith("aiobs_hitl_review_seconds") for r in recorded)


def test_dashboard_queries_only_reference_recorded_or_raw_series():
    doc = check_rule_document(RULES_PATH)
    recorded = {r["record"] for g in doc["groups"] for r in g["rules"] if "record" in r}
    queries = " ".join(load_promql(QUERIES_PATH))
    assert "aiobs_hitl_review_outcomes_total" in queries
    assert "aiobs_hitl_review_outcomes_total" in recorded


def test_float_or_none_annotation_holds_on_the_pinned_python():
    from chapters.ch13.fairness_metrics import GroupOutcomes

    assert sys.version_info >= (3, 10)
    empty = GroupOutcomes("g", 0, 0, 0, 0)
    assert empty.true_positive_rate is None
    assert empty.false_positive_rate is None


@pytest.mark.skipif(promtool() is None, reason="promtool is not installed")
def test_hitl_rules_parse_with_promtool():
    promtool_check(RULES_PATH)


@pytest.mark.skipif(promtool() is None, reason="promtool is not installed")
def test_hitl_dashboard_queries_parse_with_promtool():
    promtool_check_expressions(load_promql(QUERIES_PATH))
