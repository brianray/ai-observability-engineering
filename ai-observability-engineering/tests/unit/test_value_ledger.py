"""Unit tests: value ledger accounting."""

import pytest

from chapters.ch07_value_ledger import (
    AIValueLedger,
    cost_per_outcome_equivalents,
    ledger_to_markdown,
    table_7_3_ledger,
)


def test_table_7_3_totals_and_roi():
    ledger = table_7_3_ledger()

    assert ledger.costs() == 80000
    assert ledger.benefits() == 114700
    assert round(ledger.roi(), 2) == 0.43
    assert round(ledger.without_confidence("assumed").roi(), 2) == 0.25


def test_table_7_3_groups_assumed_value():
    assert table_7_3_ledger().by_confidence()["assumed"] == 15000


def test_benefits_cannot_use_direct_cost_confidence():
    ledger = AIValueLedger()

    with pytest.raises(ValueError):
        ledger.add_benefit("Invalid", 1, confidence="direct_cost")


def test_listing_7_2_outputs_outcome_equivalents_and_cost_per_outcome():
    payload = cost_per_outcome_equivalents()

    assert payload["outcome_equivalents"] == 12200
    assert round(payload["cost_per_outcome_usd"], 2) == 4.10
    assert payload["display"]["outcome_equivalents"] == "12,200"
    assert payload["display"]["cost_per_outcome_usd"] == "$4.10"


def test_ledger_to_markdown_includes_totals():
    markdown = ledger_to_markdown(table_7_3_ledger())

    assert markdown.startswith("| Entry | Type | Confidence | Amount (USD) |")
    assert "80,000.00" in markdown
    assert "114,700.00" in markdown
