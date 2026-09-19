"""Unit tests: Chapter 8 model router companion."""

import json

import pytest

from chapters.ch08.model_router import (
    LARGE_MODEL,
    PRICING_PATH,
    SMALL_MODEL,
    cost_estimate_usd,
    count_tokens,
    route_model,
)
from chapters.ch08_cost_engineering import chapter_opening_cost_figure_usd, table_8_1_rates


def _prompt_with_tokens(tokens: int) -> str:
    return " ".join(["tok"] * tokens)


def test_count_tokens_uses_deterministic_local_fallback_without_key():
    assert count_tokens(_prompt_with_tokens(50)) == 50


def test_count_tokens_uses_provider_endpoint_when_configured():
    def fake_post(_: str, __: dict[str, str], ___: bytes, ____: float) -> bytes:
        return b'{"input_tokens": 77}'

    assert count_tokens("hello world", api_key="key", http_post=fake_post) == 77


def test_count_tokens_falls_back_to_local_on_provider_error():
    def failing_post(_: str, __: dict[str, str], ___: bytes, ____: float) -> bytes:
        raise OSError("network down")

    assert count_tokens("hello world", api_key="key", http_post=failing_post) == 2


def test_50_token_prompt_routes_small_model():
    decision = route_model(_prompt_with_tokens(50))
    assert decision.model == SMALL_MODEL


def test_600_token_prompt_routes_large_model():
    decision = route_model(_prompt_with_tokens(600))
    assert decision.model == LARGE_MODEL


def test_force_large_overrides_threshold():
    decision = route_model(_prompt_with_tokens(50), force_large=True)
    assert decision.model == LARGE_MODEL
    assert decision.reason == "caller override"


def test_cost_estimate_matches_chapter_opening_figure():
    expected = chapter_opening_cost_figure_usd()
    observed = cost_estimate_usd(LARGE_MODEL, 1500, 400)
    assert observed == pytest.approx(expected)


def test_chapter_opening_figure_is_pricing_driven():
    pricing = json.loads(PRICING_PATH.read_text(encoding="utf-8"))
    rates = pricing["models"][LARGE_MODEL]
    expected = (1500 * rates["input_per_mtok"] + 400 * rates["output_per_mtok"]) / 1_000_000
    assert chapter_opening_cost_figure_usd() == pytest.approx(expected)


def test_table_8_1_rates_match_pricing_json():
    pricing = json.loads(PRICING_PATH.read_text(encoding="utf-8"))
    assert table_8_1_rates() == pricing["models"]
