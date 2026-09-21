"""Unit tests: Chapter 9 executive summary rendering."""

from aiobs import MockProvider
from chapters.ch07_value_ledger import table_7_3_ledger
from chapters.ch09_collect_metrics import collect_exec_summary_metrics
from chapters.ch09_exec_summary import TARGETS, render_exec_summary


def test_exec_summary_figure_9_3_renders_deterministically():
    current, prior = collect_exec_summary_metrics(
        provider=MockProvider(),
        current_ledger=table_7_3_ledger(),
        prior_ledger=table_7_3_ledger(),
    )

    rendered = render_exec_summary(current, prior)

    assert rendered["headline"] == (
        "Executive summary: ROI is 43.4%, "
        "and latency_p95_ms is the only metric off target."
    )
    assert rendered["attention"] == ["latency_p95_ms"]
    assert TARGETS["latency_p95_ms"]["source"] == "Chapter 4 scorecard latency SLO"
    assert TARGETS["roi_ratio"]["source"] == "Chapter 7 Table 7.3 measured-only ROI floor"
    assert rendered["metrics"]["assumed_value_usd"]["trend"] == "no prior period"
    assert rendered["metrics"]["tokens_per_second"]["trend"] == "flat"
    assert rendered["markdown"].startswith("# Executive summary: ROI is 43.4%")
    assert "<table>" in rendered["html"]

    for metric in rendered["metrics"].values():
        assert metric["status"] is not None
        assert metric["trend"] is not None
