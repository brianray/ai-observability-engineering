"""Generate the Chapter 8 Prometheus rules file from the price book.

Listing 8.3's dashboard queries join token-usage rates against a
``llm_token_price_usd_per_mtok`` series. That series has to come from
somewhere, and the one place it must not come from is a human retyping
``pricing.json`` into YAML. This module renders the rules file, and
``test_ch08_prometheus_artifacts.py`` fails the build when the checked-in
file and the price book disagree.
"""

from __future__ import annotations

import json
from pathlib import Path

RULES_PATH = Path(__file__).with_name("dashboard_rules.yml")
PRICING_PATH = Path(__file__).with_name("pricing.json")

#: Rendered in this order so the generated file is stable across runs.
PRICE_TYPES: tuple[tuple[str, str], ...] = (
    ("input", "input_per_mtok"),
    ("cached_input", "cached_input_per_mtok"),
    ("output", "output_per_mtok"),
)


def load_pricing(path: Path = PRICING_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def render_rules(pricing: dict | None = None) -> str:
    """Render the recording-rule group as YAML text."""
    pricing = pricing if pricing is not None else load_pricing()
    lines = [
        "# Generated from pricing.json by chapters/ch08/pricing_rules.py.",
        "# Do not hand-edit: regenerate with `python -m chapters.ch08.pricing_rules`.",
        f"# Prices retrieved_on: {pricing['retrieved_on']}",
        "groups:",
        "  - name: chapter_8_pricing",
        "    rules:",
    ]
    for model, rates in pricing["models"].items():
        for price_type, key in PRICE_TYPES:
            lines += [
                "      - record: llm_token_price_usd_per_mtok",
                f"        expr: vector({rates[key]})",
                "        labels:",
                f"          model: {model}",
                f"          price_type: {price_type}",
            ]
    return "\n".join(lines) + "\n"


def write_rules(path: Path = RULES_PATH) -> Path:
    path.write_text(render_rules(), encoding="utf-8")
    return path


if __name__ == "__main__":  # pragma: no cover - operator entry point
    print(f"wrote {write_rules()}")
