"""Unit tests: Chapter 8 token budget companion."""

import pytest

from chapters.ch08.token_budget import fit_context_to_budget, summarize_history


def _words(n: int) -> str:
    return " ".join(["tok"] * n)


def test_summarize_history_uses_mock_provider_and_returns_shorter_text():
    history = _words(40)

    summary = summarize_history(history, max_tokens=10)

    assert summary != history
    assert len(summary.split()) <= 10


def test_over_budget_trims_retrieval_first():
    def should_not_run(_: str, __: int) -> str:
        raise AssertionError("history summarization should not run when retrieval trim is enough")

    result = fit_context_to_budget(
        system_prompt=_words(20),
        question=_words(10),
        history=_words(40),
        retrieval=_words(80),
        budget_tokens=100,
        summarizer=should_not_run,
    )

    assert result.question == _words(10)
    assert result.retrieval_trimmed is True
    assert result.history_summarized is False
    assert result.total_tokens <= 100


def test_history_is_summarized_only_after_retrieval_trim_is_insufficient():
    calls = {"count": 0}

    def summarizer(history: str, max_tokens: int) -> str:
        calls["count"] += 1
        return " ".join(history.split()[:max_tokens])

    result = fit_context_to_budget(
        system_prompt=_words(20),
        question=_words(10),
        history=_words(90),
        retrieval=_words(80),
        budget_tokens=100,
        summarizer=summarizer,
    )

    assert result.retrieval_trimmed is True
    assert result.history_summarized is True
    assert calls["count"] == 1
    assert result.total_tokens <= 100


def test_raises_when_neither_trimming_nor_summary_can_fit_budget():
    with pytest.raises(ValueError):
        fit_context_to_budget(
            system_prompt=_words(120),
            question=_words(10),
            history=_words(50),
            retrieval=_words(10),
            budget_tokens=100,
            summarizer=lambda history, max_tokens: " ".join(history.split()[:max_tokens]),
        )
