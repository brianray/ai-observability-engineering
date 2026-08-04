"""Unit tests: cost accounting."""

import pytest

from aiobs.cost import CostLedger, UnknownModelError, cost_per_outcome, price_call, roi


def test_price_call_is_linear_in_tokens():
    single = price_call("mock-sonnet-1", 1000, 0)
    assert price_call("mock-sonnet-1", 2000, 0) == pytest.approx(single * 2)


def test_output_tokens_cost_more_than_input_tokens():
    assert price_call("mock-sonnet-1", 0, 1000) > price_call("mock-sonnet-1", 1000, 0)


def test_unknown_model_raises_rather_than_pricing_at_zero():
    with pytest.raises(UnknownModelError):
        price_call("model-that-does-not-exist", 100, 100)


def test_negative_tokens_rejected():
    with pytest.raises(ValueError):
        price_call("mock-sonnet-1", -1, 0)


def test_ledger_rolls_up_by_tenant():
    ledger = CostLedger()
    ledger.record("mock-sonnet-1", 1000, 500, tenant="acme")
    ledger.record("mock-sonnet-1", 1000, 500, tenant="acme")
    ledger.record("mock-sonnet-1", 1000, 500, tenant="globex")
    by_tenant = ledger.by("tenant")
    assert set(by_tenant) == {"acme", "globex"}
    assert by_tenant["acme"] == pytest.approx(by_tenant["globex"] * 2)


def test_ledger_total_matches_sum_of_records():
    ledger = CostLedger()
    for _ in range(10):
        ledger.record("mock-haiku-1", 300, 100, tenant="acme")
    assert ledger.total_usd == pytest.approx(sum(r.usd for r in ledger.records))


def test_unattributed_share():
    ledger = CostLedger()
    ledger.record("mock-sonnet-1", 1000, 0, tenant="acme")
    ledger.record("mock-sonnet-1", 1000, 0)
    assert ledger.unattributed_share() == pytest.approx(0.5)


def test_unattributed_share_of_empty_ledger_is_zero():
    assert CostLedger().unattributed_share() == 0.0


def test_rollup_by_unknown_dimension_rejected():
    with pytest.raises(ValueError):
        CostLedger().by("phase_of_the_moon")


def test_roi_and_cost_per_outcome():
    assert roi(200.0, 100.0) == pytest.approx(1.0)
    ledger = CostLedger()
    ledger.record("mock-sonnet-1", 1000, 1000, tenant="acme")
    assert cost_per_outcome(ledger, 2) == pytest.approx(ledger.total_usd / 2)


@pytest.mark.parametrize("bad", [0.0, -1.0])
def test_roi_rejects_non_positive_cost_basis(bad):
    with pytest.raises(ValueError):
        roi(100.0, bad)


def test_cost_per_outcome_rejects_zero_outcomes():
    with pytest.raises(ValueError):
        cost_per_outcome(CostLedger(), 0)
