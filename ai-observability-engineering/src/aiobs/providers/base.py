"""Provider interface.

Examples depend on this protocol, never on a concrete SDK. Swapping the
mock for a real provider is a one-line change in the example, and the
instrumentation does not move.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class ChatResponse:
    text: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    finish_reason: str = "stop"
    response_id: str = ""
    eval_scores: dict[str, float] = field(default_factory=dict)
    failure_mode: str = "none"

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@runtime_checkable
class LLMProvider(Protocol):
    """Minimum surface an example needs from a model provider."""

    name: str
    model: str

    def chat(self, prompt: str, **kwargs: Any) -> ChatResponse:
        ...

    def price(self, input_tokens: int, output_tokens: int) -> float:
        ...
