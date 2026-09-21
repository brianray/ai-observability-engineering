"""Unit tests: Chapter 8 Prometheus artifacts."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml

PRICING_PATH = Path("chapters/ch08/pricing.json")
RULES_PATH = Path("chapters/ch08/dashboard_rules.yml")
QUERIES_PATH = Path("chapters/ch08/dashboard_queries.promql")


def _promtool() -> str | None:
    return shutil.which("promtool")


def test_pricing_rules_match_pricing_json():
    pricing = json.loads(PRICING_PATH.read_text(encoding="utf-8"))["models"]
    rule_doc = yaml.safe_load(RULES_PATH.read_text(encoding="utf-8"))
    rules = rule_doc["groups"][0]["rules"]

    observed: dict[tuple[str, str], float] = {}
    for rule in rules:
        labels = rule["labels"]
        model = labels["model"]
        price_type = labels["price_type"]
        expr = rule["expr"]
        value = float(expr.removeprefix("vector(").removesuffix(")"))
        observed[(model, price_type)] = value

    for model, rates in pricing.items():
        assert observed[(model, "input")] == pytest.approx(rates["input_per_mtok"])
        assert observed[(model, "cached_input")] == pytest.approx(rates["cached_input_per_mtok"])
        assert observed[(model, "output")] == pytest.approx(rates["output_per_mtok"])


@pytest.mark.skipif(_promtool() is None, reason="promtool is not installed")
def test_prometheus_rules_parse_with_promtool():
    subprocess.run([_promtool(), "check", "rules", str(RULES_PATH)], check=True, capture_output=True)


@pytest.mark.skipif(_promtool() is None, reason="promtool is not installed")
def test_dashboard_queries_parse_with_promtool():
    expressions = [
        line.strip()
        for line in QUERIES_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    for idx, expr in enumerate(expressions):
        rule_doc = {
            "groups": [
                {
                    "name": "parse_dashboard_queries",
                    "rules": [{"record": f"dashboard_expr_{idx}", "expr": expr}],
                }
            ]
        }
        with tempfile.NamedTemporaryFile("w", suffix=".yml", delete=False, encoding="utf-8") as tmp:
            yaml.safe_dump(rule_doc, tmp)
            tmp_path = tmp.name
        try:
            subprocess.run(
                [_promtool(), "check", "rules", tmp_path],
                check=True,
                capture_output=True,
            )
        finally:
            Path(tmp_path).unlink(missing_ok=True)


def test_rules_file_is_exactly_what_the_generator_renders():
    """The checked-in YAML must be the generator's output, byte for byte.

    The prior failure mode was a hand-maintained rules file: pricing.json
    was corrected and the YAML kept the old numbers, so every dashboard
    panel priced traffic off a stale table without anything going red.
    """
    from chapters.ch08.pricing_rules import render_rules

    assert RULES_PATH.read_text(encoding="utf-8") == render_rules()


def test_every_priced_model_has_all_three_price_types():
    pricing = json.loads(PRICING_PATH.read_text(encoding="utf-8"))["models"]
    rules = yaml.safe_load(RULES_PATH.read_text(encoding="utf-8"))["groups"][0]["rules"]
    pairs = {(r["labels"]["model"], r["labels"]["price_type"]) for r in rules}

    for model in pricing:
        for price_type in ("input", "cached_input", "output"):
            assert (model, price_type) in pairs


def test_pricing_json_declares_when_it_was_retrieved():
    pricing = json.loads(PRICING_PATH.read_text(encoding="utf-8"))
    assert pricing["retrieved_on"]
    assert pricing["source"].startswith("http")
    for rates in pricing["models"].values():
        assert set(rates) == {"input_per_mtok", "cached_input_per_mtok", "output_per_mtok"}
        # A cache hit is cheaper than a fresh read on every current model.
        assert rates["cached_input_per_mtok"] < rates["input_per_mtok"]
