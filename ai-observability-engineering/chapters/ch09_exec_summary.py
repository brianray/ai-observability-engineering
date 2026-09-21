"""Chapter 9 executive summary rendering for Figure 9.3.

The ``TARGETS`` mapping is intentionally composed from prior chapters
rather than restated here: Chapter 4 defines the SLO and scorecard
thresholds, while Chapter 7 supplies the ledger-derived ROI guardrails.
That keeps the summary page tied to the same underlying definitions the
rest of the repository already demonstrates.
"""

from __future__ import annotations

from html import escape
from typing import Any

from aiobs import Aiobs, Layer, Pillar, get_tracer

from .ch04_instrumentation import slo_targets_from_ch04
from .ch07_value_ledger import ledger_targets_from_ch07
from .ch09_collect_metrics import collect_exec_summary_metrics
from .registry import example

TARGETS = {**slo_targets_from_ch04(), **ledger_targets_from_ch07()}


def _trend(current: float, prior: float | None) -> str:
    if prior is None:
        return "no prior period"
    if prior == 0:
        return "flat" if current == 0 else "+100.0%"
    percent_change = ((current - prior) / abs(prior)) * 100
    if abs(percent_change) < 2.0:
        return "flat"
    return f"{percent_change:+.1f}%"


def _status(current: float, target: float, goal: str) -> str:
    if goal == "at_most":
        return "on_target" if current <= target else "off_target"
    if goal == "at_least":
        return "on_target" if current >= target else "off_target"
    raise ValueError(f"unknown goal {goal!r}")


def _headline(attention: list[str], roi_ratio: float) -> str:
    if attention == ["latency_p95_ms"]:
        return (
            f"Executive summary: ROI is {roi_ratio * 100:.1f}%, "
            "and latency_p95_ms is the only metric off target."
        )
    if not attention:
        return f"Executive summary: ROI is {roi_ratio * 100:.1f}%, and all targets are on track."
    return (
        f"Executive summary: ROI is {roi_ratio * 100:.1f}%, "
        f"and {len(attention)} metrics need attention."
    )


def render_exec_summary(
    current: dict[str, float | str],
    prior: dict[str, float | str],
) -> dict[str, Any]:
    """Render Figure 9.3 as both Markdown and HTML."""
    metrics: dict[str, dict[str, Any]] = {}
    for name, spec in TARGETS.items():
        current_value = float(current[name])
        prior_value = prior.get(name)
        metric = {
            "current": current_value,
            "prior": None if prior_value is None else float(prior_value),
            "target": float(spec["target"]),
            "goal": spec["goal"],
            "source": spec["source"],
        }
        metric["status"] = _status(metric["current"], metric["target"], metric["goal"])
        metric["trend"] = _trend(metric["current"], metric["prior"])
        metrics[name] = metric

    attention = [name for name, metric in metrics.items() if metric["status"] == "off_target"]
    headline = _headline(attention, metrics["roi_ratio"]["current"])

    markdown_lines = [
        f"# {headline}",
        "",
        "## Attention",
        *(f"- {name}" for name in attention),
        "",
        "| Metric | Current | Target | Status | Trend | Source |",
        "| --- | ---: | ---: | --- | --- | --- |",
    ]
    for name, metric in metrics.items():
        markdown_lines.append(
            "| "
            f"{name} | {metric['current']:.3f} | {metric['target']:.3f} | "
            f"{metric['status']} | {metric['trend']} | {metric['source']} |"
        )
    markdown_lines.extend(["", "## Value ledger", str(current["ledger_markdown"])])
    markdown = "\n".join(markdown_lines)

    rows = "".join(
        "<tr>"
        f"<td>{escape(name)}</td>"
        f"<td>{metric['current']:.3f}</td>"
        f"<td>{metric['target']:.3f}</td>"
        f"<td>{escape(metric['status'])}</td>"
        f"<td>{escape(metric['trend'])}</td>"
        f"<td>{escape(str(metric['source']))}</td>"
        "</tr>"
        for name, metric in metrics.items()
    )
    attention_items = "".join(f"<li>{escape(name)}</li>" for name in attention)
    html = (
        "<section>"
        f"<h1>{escape(headline)}</h1>"
        "<h2>Attention</h2>"
        f"<ul>{attention_items}</ul>"
        "<table>"
        "<thead><tr><th>Metric</th><th>Current</th><th>Target</th>"
        "<th>Status</th><th>Trend</th><th>Source</th></tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table>"
        "<h2>Value ledger</h2>"
        f"<pre>{escape(str(current['ledger_markdown']))}</pre>"
        "</section>"
    )
    return {
        "headline": headline,
        "attention": attention,
        "metrics": metrics,
        "markdown": markdown,
        "html": html,
    }


@example(
    chapter=9,
    key="exec_summary_page",
    title="Rendering the executive summary page",
    pillar=Pillar.ROI,
    layer=Layer.BUSINESS_AND_OUTCOMES,
    listing="9.3",
)
def exec_summary_page() -> dict[str, Any]:
    tracer = get_tracer(__name__)
    with tracer.start_as_current_span("exec_summary_page") as span:
        span.set_attribute(Aiobs.PILLAR, Pillar.ROI.value)
        span.set_attribute(Aiobs.LAYER, Layer.BUSINESS_AND_OUTCOMES.value)
        current, prior = collect_exec_summary_metrics()
        rendered = render_exec_summary(current, prior)
        span.set_attribute("aiobs.exec.attention_count", len(rendered["attention"]))
        span.set_attribute("aiobs.value.roi_ratio", rendered["metrics"]["roi_ratio"]["current"])

    return rendered
