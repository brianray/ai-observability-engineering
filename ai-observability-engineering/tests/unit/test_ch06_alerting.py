"""Unit tests: Chapter 6 alerting tiers."""

from chapters.ch06 import AlertMetrics, evaluate_alert_tier


def test_informational_tier_triggers_for_single_drift_signal():
    metrics = AlertMetrics(
        psi_scores={"prompt_length": 0.12},
        ks_p_values={"prompt_length": 0.20},
        embedding_drift_score=0.05,
    )
    assert evaluate_alert_tier(metrics) == "informational"


def test_warning_tier_triggers_for_two_embedding_windows():
    metrics = AlertMetrics(
        psi_scores={"prompt_length": 0.08},
        ks_p_values={"prompt_length": 0.20},
        embedding_drift_score=0.18,
        embedding_drift_score_previous_window=0.17,
    )
    assert evaluate_alert_tier(metrics) == "warning"


def test_critical_tier_triggers_for_warning_plus_eval_regression():
    metrics = AlertMetrics(
        psi_scores={"prompt_length": 0.30},
        ks_p_values={"prompt_length": 0.20},
        embedding_drift_score=0.12,
        groundedness=0.58,
        groundedness_slo_floor=0.70,
    )
    assert evaluate_alert_tier(metrics) == "critical"


def test_retraining_trigger_requires_human_confirmation():
    metrics = AlertMetrics(
        psi_scores={"prompt_length": 0.30},
        ks_p_values={"prompt_length": 0.20},
        embedding_drift_score=0.12,
        groundedness=0.58,
        groundedness_slo_floor=0.70,
        human_confirmation=True,
    )
    assert evaluate_alert_tier(metrics) == "retraining_trigger"


def test_seasonal_baseline_suppresses_escalation_beyond_informational():
    metrics = AlertMetrics(
        psi_scores={"holiday_queries": 0.31},
        ks_p_values={"holiday_queries": 0.01},
        embedding_drift_score=0.18,
        embedding_drift_score_previous_window=0.17,
        groundedness=0.55,
        groundedness_slo_floor=0.70,
        seasonal_baseline_match=True,
    )
    assert evaluate_alert_tier(metrics) == "informational"
