"""Tiered Chapter 6 drift alerting driven by the table-backed YAML rules."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]


@dataclass(frozen=True)
class AlertMetrics:
    """Inputs needed to evaluate the highest triggered drift alert tier.

    Drift alone is not enough to page someone. The metrics bundle keeps
    the raw drift scores, the Chapter 4 eval guardrails, and a small
    amount of persistence context together so the evaluator can suppress
    known seasonal baselines while still escalating novel movement.
    """

    psi_scores: dict[str, float] = field(default_factory=dict)
    ks_p_values: dict[str, float] = field(default_factory=dict)
    embedding_drift_score: float = 0.0
    embedding_drift_score_previous_window: float | None = None
    groundedness: float = 1.0
    groundedness_slo_floor: float = 0.0
    hallucination_rate: float = 0.0
    hallucination_rate_slo_ceiling: float = 1.0
    seasonal_baseline_match: bool = False
    human_confirmation: bool = False


def load_alerting_rules() -> list[dict[str, Any]]:
    """Load the chapter's alerting tiers from the book-aligned YAML file."""

    path = Path(__file__).with_name("alerting_rules.yaml")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    tiers = payload.get("tiers", [])
    if not isinstance(tiers, list):
        raise ValueError("alerting rules must define a top-level 'tiers' list")
    return tiers


def _has_input_feature_drift(metrics: AlertMetrics, ks_threshold: float, psi_threshold: float) -> bool:
    return any(value < ks_threshold for value in metrics.ks_p_values.values()) or any(
        value > psi_threshold for value in metrics.psi_scores.values()
    )


def _warning_condition(metrics: AlertMetrics, rules: dict[str, Any]) -> bool:
    if metrics.seasonal_baseline_match:
        return False

    psi_threshold = float(rules["psi_threshold"])
    embedding_threshold = float(rules["embedding_drift_threshold"])
    previous = metrics.embedding_drift_score_previous_window
    embedding_consecutive = (
        previous is not None
        and previous > embedding_threshold
        and metrics.embedding_drift_score > embedding_threshold
    )
    return embedding_consecutive or any(value > psi_threshold for value in metrics.psi_scores.values())


def _eval_regression(metrics: AlertMetrics) -> bool:
    return (
        metrics.groundedness < metrics.groundedness_slo_floor
        or metrics.hallucination_rate > metrics.hallucination_rate_slo_ceiling
    )


def evaluate_alert_tier(metrics: AlertMetrics) -> str | None:
    """Return the highest alert tier triggered by the supplied daily metrics."""

    rules = {tier["name"]: tier["condition"] for tier in load_alerting_rules()}

    if (
        metrics.human_confirmation
        and _warning_condition(metrics, rules["warning"])
        and _eval_regression(metrics)
    ):
        return "retraining_trigger"

    if _warning_condition(metrics, rules["warning"]) and _eval_regression(metrics):
        return "critical"

    if _warning_condition(metrics, rules["warning"]):
        return "warning"

    informational = rules["informational"]
    if _has_input_feature_drift(
        metrics,
        float(informational["ks_p_threshold"]),
        float(informational["psi_threshold"]),
    ) or metrics.embedding_drift_score > float(informational["embedding_drift_threshold"]):
        return "informational"

    return None
