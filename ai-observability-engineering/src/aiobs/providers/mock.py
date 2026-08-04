"""A deterministic mock LLM provider.

Every example in this book runs without an API key. That is deliberate:
an observability book whose examples cost money to run does not get run.
The mock is seeded, so the same input always produces the same output,
the same token counts, and the same eval scores. Tests can therefore
assert on exact values.

It also knows how to fail. ``FailureMode`` reproduces the specific
production failures the book keeps returning to: the confidently wrong
answer that returns a clean 200, the silent retry loop, the slow drift
in output distribution.
"""

from __future__ import annotations

import hashlib
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .base import ChatResponse, LLMProvider

DEFAULT_MODEL = "mock-sonnet-1"


class FailureMode(str, Enum):
    """Scripted failure modes. See ``docs/TESTING.md``."""

    NONE = "none"
    #: Fluent, well formed, factually wrong. Status 200, latency normal.
    CONFIDENTLY_WRONG = "confidently_wrong"
    #: Answer not supported by the retrieved context.
    UNGROUNDED = "ungrounded"
    #: Agent repeats a step without progress (MAST FM-1.3).
    RETRY_LOOP = "retry_loop"
    #: Agent does not recognize the task is finished (MAST FM-1.5).
    NO_TERMINATION = "no_termination"
    #: Output distribution shifts relative to the reference window.
    DRIFT = "drift"
    #: Latency spike with a correct answer.
    SLOW = "slow"
    #: Hard failure. The only mode a traditional APM tool would catch.
    ERROR = "error"


@dataclass
class MockProvider(LLMProvider):
    """Seeded, offline, scriptable stand-in for a real LLM API."""

    model: str = DEFAULT_MODEL
    seed: int = 1729
    failure_mode: FailureMode = FailureMode.NONE
    latency_ms: float = 0.0
    input_price_per_1k: float = 0.003
    output_price_per_1k: float = 0.015
    call_count: int = field(default=0, init=False)

    name: str = "mock"

    def _rng(self, prompt: str) -> random.Random:
        digest = hashlib.sha256(f"{self.seed}:{prompt}".encode()).hexdigest()
        return random.Random(int(digest[:16], 16))

    @staticmethod
    def count_tokens(text: str) -> int:
        """Deterministic stand-in for a real tokenizer: ~4 chars per token."""
        return max(1, (len(text) + 3) // 4)

    def chat(
        self,
        prompt: str,
        *,
        context: str | None = None,
        max_tokens: int = 512,
        **_: Any,
    ) -> ChatResponse:
        self.call_count += 1
        rng = self._rng(prompt)

        if self.failure_mode is FailureMode.ERROR:
            raise RuntimeError("mock provider: upstream 503")

        if self.latency_ms or self.failure_mode is FailureMode.SLOW:
            time.sleep(min((self.latency_ms or 250.0), 50.0) / 1000.0)

        text, scores = self._generate(prompt, context, rng)
        input_tokens = self.count_tokens(prompt + (context or ""))
        output_tokens = min(max_tokens, self.count_tokens(text))

        return ChatResponse(
            text=text,
            model=self.model,
            provider=self.name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            finish_reason="length" if output_tokens >= max_tokens else "stop",
            response_id=f"mock-{rng.getrandbits(32):08x}",
            eval_scores=scores,
            failure_mode=self.failure_mode.value,
        )

    def _generate(
        self, prompt: str, context: str | None, rng: random.Random
    ) -> tuple[str, dict[str, float]]:
        mode = self.failure_mode

        if mode is FailureMode.CONFIDENTLY_WRONG:
            return (
                "Yes, that policy is still in effect and the extension applies.",
                {"hallucination": 0.81, "groundedness": 0.12, "relevance": 0.88},
            )
        if mode is FailureMode.UNGROUNDED:
            return (
                "Based on the documentation, the limit is 90 days.",
                {"hallucination": 0.44, "groundedness": 0.21, "relevance": 0.72},
            )
        if mode is FailureMode.RETRY_LOOP:
            return (
                "Let me check that again. Let me check that again.",
                {"hallucination": 0.30, "groundedness": 0.40, "relevance": 0.25},
            )
        if mode is FailureMode.NO_TERMINATION:
            return (
                "I will continue verifying before giving a final answer.",
                {"hallucination": 0.18, "groundedness": 0.55, "relevance": 0.35},
            )
        if mode is FailureMode.DRIFT:
            drift_noise = rng.random() * 0.5
            return (
                "The answer depends on the current configuration.",
                {
                    "hallucination": 0.20 + drift_noise,
                    "groundedness": 0.90 - drift_noise,
                    "relevance": 0.70,
                },
            )

        # The healthy path answers *from the context*, so a groundedness
        # evaluator scores it high. That is the whole contrast the book
        # draws: a grounded answer and a fluent one look identical to an
        # APM tool and completely different to an eval.
        if context:
            sentences = [s.strip() for s in context.split(".") if s.strip()]
            body = sentences[0] if sentences else context
            text = f"{body}."
            scores = {"hallucination": 0.03, "groundedness": 0.91, "relevance": 0.94}
        else:
            text = "I do not have a source for that."
            scores = {"hallucination": 0.05, "groundedness": 0.0, "relevance": 0.40}
        return text, scores

    def price(self, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens / 1000.0 * self.input_price_per_1k
            + output_tokens / 1000.0 * self.output_price_per_1k
        )
