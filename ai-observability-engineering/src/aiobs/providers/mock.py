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
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

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


@dataclass(frozen=True)
class MockCompletionUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class MockChoiceDelta:
    content: str | None = None
    role: str | None = None


@dataclass(frozen=True)
class MockChoice:
    delta: MockChoiceDelta
    index: int = 0
    finish_reason: str | None = None


@dataclass(frozen=True)
class MockChatChunk:
    id: str
    choices: list[MockChoice]
    created: int
    model: str
    usage: MockCompletionUsage | None = None
    object: str = "chat.completion.chunk"


class StreamClock(Protocol):
    def now(self) -> float: ...

    def sleep(self, seconds: float) -> None: ...


class _SystemClock:
    def now(self) -> float:
        return time.perf_counter()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


@dataclass
class MockProvider(LLMProvider):
    """Seeded, offline, scriptable stand-in for a real LLM API."""

    model: str = DEFAULT_MODEL
    seed: int = 1729
    failure_mode: FailureMode = FailureMode.NONE
    latency_ms: float = 0.0
    input_price_per_1k: float = 0.003
    output_price_per_1k: float = 0.015
    retry_fraction: float = 0.0
    stream_completion_tokens: int = 4
    stream_chunk_latency_ms: float = 20.0
    call_count: int = field(default=0, init=False)

    name: str = "mock"

    def _rng(self, prompt: str) -> random.Random:
        digest = hashlib.sha256(f"{self.seed}:{prompt}".encode()).hexdigest()
        return random.Random(int(digest[:16], 16))

    @staticmethod
    def count_tokens(text: str) -> int:
        """Deterministic stand-in for a real tokenizer: ~4 chars per token."""
        return max(1, (len(text) + 3) // 4)

    def _should_retry(self, prompt: str) -> bool:
        if self.retry_fraction <= 0.0:
            return False
        if self.retry_fraction >= 1.0:
            return True
        return self._rng(prompt).random() < self.retry_fraction

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
        attempts = 2 if self._should_retry(prompt) else 1
        single_attempt_input_tokens = self.count_tokens(prompt + (context or ""))
        single_attempt_output_tokens = min(max_tokens, self.count_tokens(text))
        input_tokens = single_attempt_input_tokens * attempts
        output_tokens = single_attempt_output_tokens * attempts

        return ChatResponse(
            text=text,
            model=self.model,
            provider=self.name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            attempts=attempts,
            attempt_models=tuple(self.model for _ in range(attempts)),
            finish_reason="length" if output_tokens >= max_tokens else "stop",
            response_id=f"mock-{rng.getrandbits(32):08x}",
            eval_scores=scores,
            failure_mode=self.failure_mode.value,
        )

    @staticmethod
    def _split_stream_text(text: str, parts: int) -> list[str]:
        parts = max(1, min(parts, len(text)))
        chunks: list[str] = []
        start = 0
        for index in range(parts):
            if index == parts - 1:
                chunks.append(text[start:])
                break
            remaining_chars = len(text) - start
            remaining_parts = parts - index
            width = max(1, remaining_chars // remaining_parts)
            end = start + width
            chunks.append(text[start:end])
            start = end
        return chunks

    def stream_chat(
        self,
        prompt: str,
        *,
        context: str | None = None,
        max_tokens: int = 512,
        stream_options: dict[str, bool] | None = None,
        clock: StreamClock | None = None,
        **_: Any,
    ) -> Iterator[MockChatChunk]:
        self.call_count += 1
        rng = self._rng(prompt)

        if self.failure_mode is FailureMode.ERROR:
            raise RuntimeError("mock provider: upstream 503")

        active_clock = clock or _SystemClock()
        if self.latency_ms or self.failure_mode is FailureMode.SLOW:
            active_clock.sleep(min((self.latency_ms or 250.0), 50.0) / 1000.0)

        text, _scores = self._generate(prompt, context, rng)
        input_tokens = self.count_tokens(prompt + (context or ""))
        completion_tokens = max(1, min(max_tokens, self.stream_completion_tokens))
        content_chunks = self._split_stream_text(text, completion_tokens)
        response_id = f"mock-{rng.getrandbits(32):08x}"
        created = int(rng.random() * 1_000_000)

        yield MockChatChunk(
            id=response_id,
            choices=[MockChoice(delta=MockChoiceDelta(role="assistant", content=""))],
            created=created,
            model=self.model,
        )

        for index, content in enumerate(content_chunks):
            active_clock.sleep(self.stream_chunk_latency_ms / 1000.0)
            yield MockChatChunk(
                id=response_id,
                choices=[
                    MockChoice(
                        delta=MockChoiceDelta(content=content),
                        finish_reason="stop" if index == len(content_chunks) - 1 else None,
                    )
                ],
                created=created,
                model=self.model,
            )

        if stream_options and stream_options.get("include_usage"):
            active_clock.sleep(self.stream_chunk_latency_ms / 1000.0)
            yield MockChatChunk(
                id=response_id,
                choices=[],
                created=created,
                model=self.model,
                usage=MockCompletionUsage(
                    prompt_tokens=input_tokens,
                    completion_tokens=len(content_chunks),
                    total_tokens=input_tokens + len(content_chunks),
                ),
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
