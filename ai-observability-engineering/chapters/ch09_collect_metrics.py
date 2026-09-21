"""Chapter 9 collector inputs for the executive summary page."""

from __future__ import annotations

from aiobs import MockProvider

from .ch03_signals import prometheus_signal_snapshot
from .ch04_instrumentation import chapter_4_scorecard
from .ch07_value_ledger import AIValueLedger, ledger_summary_metrics, table_7_3_ledger


def _period_metrics(
    *,
    period: str,
    provider: MockProvider,
    ledger: AIValueLedger,
) -> dict[str, float | str]:
    return {
        **prometheus_signal_snapshot(provider, period=period),
        **chapter_4_scorecard(provider, period=period),
        **ledger_summary_metrics(ledger),
    }


def collect_exec_summary_metrics(
    *,
    provider: MockProvider | None = None,
    current_ledger: AIValueLedger | None = None,
    prior_ledger: AIValueLedger | None = None,
) -> tuple[dict[str, float | str], dict[str, float | str]]:
    """Collect deterministic current and prior metrics for Figure 9.3."""
    active_provider = provider or MockProvider()
    current = _period_metrics(
        period="current",
        provider=active_provider,
        ledger=current_ledger or table_7_3_ledger(),
    )
    prior = _period_metrics(
        period="prior",
        provider=active_provider,
        ledger=prior_ledger or table_7_3_ledger(),
    )
    prior.pop("assumed_value_usd", None)
    return current, prior
