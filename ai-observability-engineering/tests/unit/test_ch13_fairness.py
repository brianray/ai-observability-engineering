"""Unit tests: Chapter 13 fairness companion."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from chapters.ch13 import (
    GAUGE_LABELS,
    GroupOutcomes,
    evaluate_rag_quality,
    publish_fairness,
)
from chapters.ch13.rag_quality import FIXTURES
from tests.support.prometheus import check_rule_document, promtool, promtool_check

ALERTS_PATH = Path("chapters/ch13/fairness_alerts.yaml")


# --- RAG quality ---


def test_eval_runs_over_six_fixed_samples():
    assert len(FIXTURES) == 6
    assert evaluate_rag_quality().sample_count == 6


def test_hallucination_rate_is_exactly_one_minus_faithfulness():
    """Not two signals. One signal and its complement."""
    result = evaluate_rag_quality()
    assert result.hallucination_rate == pytest.approx(1.0 - result.faithfulness_mean)
    assert result.faithfulness_mean == pytest.approx(4 / 6)
    assert result.hallucination_rate == pytest.approx(2 / 6)


def test_the_mock_judge_is_deterministic():
    first = evaluate_rag_quality()
    for _ in range(5):
        assert evaluate_rag_quality() == first


def test_relevancy_does_not_track_grounding():
    """An invented answer can be perfectly on topic."""
    result = evaluate_rag_quality()
    assert result.answer_relevancy_mean > result.faithfulness_mean


def test_an_empty_eval_raises():
    with pytest.raises(ValueError):
        evaluate_rag_quality(samples=[])


# --- fairness publishing ---


@pytest.fixture()
def four_groups():
    """Three measurable, one below min_n."""
    return [
        GroupOutcomes("group_a", true_positives=40, false_positives=20,
                      true_negatives=100, false_negatives=40),
        GroupOutcomes("group_b", true_positives=30, false_positives=40,
                      true_negatives=90, false_negatives=40),
        GroupOutcomes("group_c", true_positives=20, false_positives=10,
                      true_negatives=150, false_negatives=20),
        GroupOutcomes("group_d", true_positives=3, false_positives=2,
                      true_negatives=5, false_negatives=1),
    ]


def test_all_four_gauges_are_set_with_documented_labels(four_groups):
    _, recorder = publish_fairness(four_groups)
    assert recorder.names() == set(GAUGE_LABELS)


def test_a_small_group_publishes_sample_size_only(four_groups):
    report, recorder = publish_fairness(four_groups)

    assert report.suppressed_groups == ("group_d",)
    assert recorder.get("aiobs_fairness_sample_size", group="group_d") == 11.0
    assert recorder.get("aiobs_fairness_positive_rate", group="group_d") is None


def test_every_group_still_publishes_its_sample_size(four_groups):
    """A group that vanishes entirely is a group nobody notices is missing."""
    _, recorder = publish_fairness(four_groups)
    for group in four_groups:
        assert recorder.get("aiobs_fairness_sample_size", group=group.group) == float(group.n)


def test_parity_gap_is_max_minus_min_across_measurable_groups_only(four_groups):
    report, _ = publish_fairness(four_groups)

    assert set(report.positive_rates) == {"group_a", "group_b", "group_c"}
    rates = list(report.positive_rates.values())
    assert report.parity_gap == pytest.approx(max(rates) - min(rates))
    # group_d's rate (5/11 = 0.45) would have widened the gap. Including a
    # suppressed group is how a disclosure rule fabricates a disparity.
    assert report.parity_gap == pytest.approx(0.35 - 0.15)


def test_equalized_odds_gap_is_the_larger_of_the_tpr_and_fpr_gaps(four_groups):
    report, recorder = publish_fairness(four_groups)

    assert report.equalized_odds_gap == pytest.approx(max(report.tpr_gap, report.fpr_gap))
    assert report.equalized_odds_gap == pytest.approx(report.fpr_gap)
    assert report.equalized_odds_gap > report.tpr_gap
    assert recorder.get("aiobs_fairness_equalized_odds_gap") == pytest.approx(
        report.equalized_odds_gap
    )


def test_averaging_would_have_hidden_the_larger_gap(four_groups):
    """The reason equalized odds takes the max rather than the mean."""
    report, _ = publish_fairness(four_groups)
    mean_of_gaps = (report.tpr_gap + report.fpr_gap) / 2
    assert report.equalized_odds_gap > mean_of_gaps


def test_min_n_is_configurable(four_groups):
    report, recorder = publish_fairness(four_groups, min_n=5)
    assert report.suppressed_groups == ()
    assert recorder.get("aiobs_fairness_positive_rate", group="group_d") is not None


def test_a_gauge_rejects_an_undeclared_label_set(four_groups):
    _, recorder = publish_fairness(four_groups)
    with pytest.raises(ValueError):
        recorder.set("aiobs_fairness_parity_gap", 0.1, group="group_a")
    with pytest.raises(KeyError):
        recorder.set("aiobs_fairness_not_a_gauge", 0.1)


# --- alerting rules ---


def test_fairness_alerts_are_structurally_valid():
    check_rule_document(ALERTS_PATH)


def test_alerts_cover_both_gaps_and_the_metric_going_absent():
    doc = check_rule_document(ALERTS_PATH)
    alerts = {r["alert"] for g in doc["groups"] for r in g["rules"] if "alert" in r}
    assert "DemographicParityGapHigh" in alerts
    assert "EqualizedOddsGapHigh" in alerts
    # A fairness metric that stops being published looks exactly like a
    # fairness problem that resolved itself.
    assert "FairnessMetricsAbsent" in alerts


def test_alert_expressions_reference_gauges_this_chapter_publishes():
    doc = check_rule_document(ALERTS_PATH)
    exprs = " ".join(r["expr"] for g in doc["groups"] for r in g["rules"])
    for gauge in ("aiobs_fairness_parity_gap", "aiobs_fairness_equalized_odds_gap"):
        assert gauge in exprs, f"{gauge} is published but never alerted on"
    for gauge in GAUGE_LABELS:
        if gauge in exprs:
            continue
        assert gauge == "aiobs_fairness_positive_rate", (
            f"{gauge} is published but nothing references it"
        )


@pytest.mark.skipif(promtool() is None, reason="promtool is not installed")
def test_fairness_alerts_parse_with_promtool():
    promtool_check(ALERTS_PATH)


# --- ragas surface ---

_HAS_RAGAS = importlib.util.find_spec("ragas") is not None


@pytest.mark.skipif(not _HAS_RAGAS, reason="ragas is an optional extra")
def test_pinned_ragas_surface_still_holds():
    """Fails the build the day Listing 13.2 goes stale."""
    import ragas

    from chapters.ch13.ragas_compat import METRIC_RESULT_COLUMNS, TOP_LEVEL_IMPORTS

    for name in TOP_LEVEL_IMPORTS:
        assert hasattr(ragas, name), f"ragas no longer exports {name}"

    from ragas import metrics

    for class_name, column in METRIC_RESULT_COLUMNS.items():
        metric_cls = getattr(metrics, class_name)
        assert metric_cls().name == column, (
            f"{class_name} now produces column {metric_cls().name!r}, not {column!r}"
        )
