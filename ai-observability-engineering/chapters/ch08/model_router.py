"""Dynamic model router: cheap model for simple queries, powerful for complex.

Companion file: chapters/ch08/model_router.py
Companion file: chapters/ch08_cost_engineering.py -- https://github.com/brianray/ai-observability-engineering/blob/main/chapters/ch08_cost_engineering.py
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

PRICING_PATH = Path(__file__).with_name("pricing.json")
PRICING = json.loads(PRICING_PATH.read_text(encoding="utf-8"))

SMALL_MODEL = "claude-haiku-4-5"
LARGE_MODEL = "claude-sonnet-4-5"
COMPLEXITY_TOKEN_THRESHOLD = 300

_ANTHROPIC_COUNT_TOKENS_ENDPOINT = "https://api.anthropic.com/v1/messages/count_tokens"

HttpPost = Callable[[str, dict[str, str], bytes, float], bytes]
TokenCounter = Callable[[str], int]


@dataclass
class RoutingDecision:
    model: str
    reason: str
    estimated_cost_usd: float


def cost_estimate_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimated cost from the externalized rate table (USD per million tokens)."""
    rates = PRICING["models"][model]
    return (
        input_tokens * rates["input_per_mtok"] + output_tokens * rates["output_per_mtok"]
    ) / 1_000_000


def route_model(
    prompt: str,
    expected_output_tokens: int = 300,
    force_large: bool = False,
) -> RoutingDecision:
    """Route on a token-count complexity proxy.

    This is a deliberately simple first heuristic: short prompts go to the
    small model, long prompts to the large one. It is wrong for prompts that
    are short but conceptually hard, which is why every routing rule must be
    validated against the eval loop before it reaches production.
    """
    input_tokens = count_tokens(prompt)
    if force_large:
        model, reason = LARGE_MODEL, "caller override"
    elif input_tokens < COMPLEXITY_TOKEN_THRESHOLD:
        model, reason = SMALL_MODEL, f"input {input_tokens} tokens below threshold"
    else:
        model, reason = LARGE_MODEL, f"input {input_tokens} tokens at or above threshold"

    return RoutingDecision(
        model=model,
        reason=reason,
        estimated_cost_usd=cost_estimate_usd(model, input_tokens, expected_output_tokens),
    )


def _local_count_tokens(text: str) -> int:
    words = re.findall(r"\S+", text)
    return len(words)


def _urllib_post(url: str, headers: dict[str, str], payload: bytes, timeout: float) -> bytes:
    request = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _provider_count_tokens(
    text: str,
    *,
    model: str,
    endpoint: str,
    api_key: str,
    timeout_s: float,
    http_post: HttpPost,
) -> int:
    payload = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": text}],
        }
    ).encode("utf-8")
    headers = {
        "content-type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    body = http_post(endpoint, headers, payload, timeout_s)
    parsed = json.loads(body.decode("utf-8"))
    return int(parsed["input_tokens"])


def count_tokens(
    text: str,
    *,
    model: str = LARGE_MODEL,
    endpoint: str | None = None,
    api_key: str | None = None,
    timeout_s: float = 5.0,
    http_post: HttpPost = _urllib_post,
    local_counter: TokenCounter = _local_count_tokens,
) -> int:
    """Count tokens with provider API when configured, else deterministic local fallback."""
    if not text:
        return 0

    resolved_api_key = api_key or os.getenv("AIOBS_ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    resolved_endpoint = (
        endpoint or os.getenv("AIOBS_COUNT_TOKENS_ENDPOINT") or _ANTHROPIC_COUNT_TOKENS_ENDPOINT
    )

    if not resolved_api_key or not resolved_endpoint:
        return local_counter(text)

    try:
        return _provider_count_tokens(
            text,
            model=model,
            endpoint=resolved_endpoint,
            api_key=resolved_api_key,
            timeout_s=timeout_s,
            http_post=http_post,
        )
    except (KeyError, ValueError, TypeError, OSError, urllib.error.URLError, TimeoutError):
        return local_counter(text)
