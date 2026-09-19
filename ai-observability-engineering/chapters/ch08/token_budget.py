"""Token budget controls for context assembly (Listing 8.2 companion)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from aiobs.providers.mock import MockProvider

from .model_router import count_tokens

TokenCounter = Callable[[str], int]
Summarizer = Callable[[str, int], str]


@dataclass(frozen=True)
class BudgetedContext:
    system_prompt: str
    history: str
    retrieval: str
    total_tokens: int
    retrieval_trimmed: bool
    history_summarized: bool


def _trim_to_token_limit(text: str, token_limit: int, token_counter: TokenCounter) -> str:
    if token_limit <= 0:
        return ""

    words = text.split()
    while words and token_counter(" ".join(words)) > token_limit:
        words.pop()
    return " ".join(words)


def summarize_history(
    history: str,
    max_tokens: int,
    *,
    provider: MockProvider | None = None,
    token_counter: TokenCounter = count_tokens,
) -> str:
    """Deterministic summarization stub wired to MockProvider."""
    if max_tokens < 0:
        raise ValueError("max_tokens must be non-negative")

    mock = provider or MockProvider(model="mock-haiku-1")
    mock.chat(
        "Summarize the conversation history for context budgeting.",
        context=history,
    )
    return _trim_to_token_limit(history, max_tokens, token_counter)


def fit_context_to_budget(
    *,
    system_prompt: str,
    history: str,
    retrieval: str,
    token_budget: int,
    token_counter: TokenCounter = count_tokens,
    summarizer: Summarizer = summarize_history,
) -> BudgetedContext:
    """Trim retrieval first, then summarize history if needed, else fail loudly."""
    if token_budget <= 0:
        raise ValueError("token_budget must be positive")

    current_history = history
    current_retrieval = retrieval

    def _total_tokens() -> int:
        return (
            token_counter(system_prompt)
            + token_counter(current_history)
            + token_counter(current_retrieval)
        )

    if _total_tokens() <= token_budget:
        return BudgetedContext(
            system_prompt=system_prompt,
            history=current_history,
            retrieval=current_retrieval,
            total_tokens=_total_tokens(),
            retrieval_trimmed=False,
            history_summarized=False,
        )

    allowed_retrieval_tokens = token_budget - token_counter(system_prompt) - token_counter(current_history)
    trimmed_retrieval = _trim_to_token_limit(
        current_retrieval,
        allowed_retrieval_tokens,
        token_counter,
    )
    retrieval_trimmed = trimmed_retrieval != current_retrieval
    current_retrieval = trimmed_retrieval

    if _total_tokens() <= token_budget:
        return BudgetedContext(
            system_prompt=system_prompt,
            history=current_history,
            retrieval=current_retrieval,
            total_tokens=_total_tokens(),
            retrieval_trimmed=retrieval_trimmed,
            history_summarized=False,
        )

    allowed_history_tokens = token_budget - token_counter(system_prompt) - token_counter(current_retrieval)
    summarized_history = summarizer(current_history, max(0, allowed_history_tokens))
    history_summarized = summarized_history != current_history
    current_history = summarized_history

    if _total_tokens() <= token_budget and history_summarized:
        return BudgetedContext(
            system_prompt=system_prompt,
            history=current_history,
            retrieval=current_retrieval,
            total_tokens=_total_tokens(),
            retrieval_trimmed=retrieval_trimmed,
            history_summarized=True,
        )

    raise ValueError("context cannot fit within token_budget after retrieval trim and history summary")
