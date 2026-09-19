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
RULES_PATH = Path("chapters/ch08/pricing_rules.yml")
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
        token_type = labels["token_type"]
        expr = rule["expr"]
        value = float(expr.removeprefix("vector(").removesuffix(")"))
        observed[(model, token_type)] = value

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
