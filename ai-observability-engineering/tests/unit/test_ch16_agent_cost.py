"""Unit tests: Chapter 16 tool, memory, and failure-control companion."""

from __future__ import annotations

import pytest

from aiobs import Operation, capture
from aiobs.semconv import SEMCONV_VERSION, GenAI
from chapters.ch16 import (
    DEFAULT_RELEVANCE_THRESHOLD,
    PREVIEW_BYTES,
    CircuitOpen,
    ContextMetrics,
    LocalVectorStore,
    LoopSignatureBreaker,
    MemoryItem,
    MemoryMetrics,
    ObservableTool,
    ToolCounter,
    args_hash,
    text_similarity,
)
from chapters.ch16.extra_breakers import BudgetExceeded, CostBreaker, ElapsedTimeBreaker


@pytest.fixture()
def counter():
    return ToolCounter()


def _tool(counter, func=None, **kw):
    return ObservableTool(
        name="lookup", func=func or (lambda **kwargs: {"ok": True}), counter=counter, **kw
    )


# --- circuit breaker ---


def test_fourth_call_raises_and_records_breaker_open(counter):
    tool = _tool(counter, max_calls=3)
    for _ in range(3):
        tool()

    with pytest.raises(CircuitOpen):
        tool()

    assert counter.get("lookup", "breaker_open") == 1
    assert counter.get("lookup", "ok") == 3


def test_reset_allows_the_next_run(counter):
    tool = _tool(counter, max_calls=3)
    for _ in range(3):
        tool()
    with pytest.raises(CircuitOpen):
        tool()

    tool.reset()
    assert tool() == {"ok": True}


def test_an_erroring_tool_records_the_error_outcome(counter):
    def boom(**_):
        raise RuntimeError("upstream down")

    tool = _tool(counter, func=boom)
    with pytest.raises(RuntimeError):
        tool()
    assert counter.get("lookup", "error") == 1


# --- previews and hashing ---


def test_previews_never_exceed_the_byte_cap(counter):
    tool = _tool(counter, func=lambda **kw: "z" * 10_000)
    with capture() as spans:
        tool(query="q" * 10_000)

    attrs = dict(spans[0].attributes or {})
    assert len(attrs["aiobs.tool.args_preview"].encode()) <= PREVIEW_BYTES
    assert len(attrs["aiobs.tool.result_preview"].encode()) <= PREVIEW_BYTES


def test_previews_pass_through_the_tools_redactor(counter):
    def redact(text: str) -> str:
        return text.replace("4111111111111111", "[redacted]")

    tool = _tool(
        counter,
        func=lambda **kw: "card 4111111111111111 on file",
        redactor=redact,
    )
    with capture() as spans:
        tool(card="4111111111111111")

    attrs = dict(spans[0].attributes or {})
    assert "4111111111111111" not in attrs["aiobs.tool.args_preview"]
    assert "4111111111111111" not in attrs["aiobs.tool.result_preview"]
    assert "[redacted]" in attrs["aiobs.tool.result_preview"]


def test_redaction_happens_before_truncation(counter):
    """Truncating first can slice a pattern in half and leak the tail."""
    secret = "4111111111111111"
    padding = "p" * (PREVIEW_BYTES - 10)

    def redact(text: str) -> str:
        return text.replace(secret, "[redacted]")

    tool = _tool(counter, func=lambda **kw: f"{padding}{secret}", redactor=redact)
    with capture() as spans:
        tool()

    assert secret not in dict(spans[0].attributes or {})["aiobs.tool.result_preview"]


def test_args_hash_is_stable_across_kwargs_order():
    assert args_hash((), {"a": 1, "b": 2}) == args_hash((), {"b": 2, "a": 1})
    assert args_hash((), {"a": 1}) != args_hash((), {"a": 2})


def test_args_hash_reaches_the_span(counter):
    tool = _tool(counter)
    with capture() as spans:
        tool(query="refunds")
    attrs = dict(spans[0].attributes or {})
    assert attrs["aiobs.tool.args_hash"] == args_hash((), {"query": "refunds"})


# --- semantic conventions ---


def test_tool_spans_use_the_pinned_genai_convention(counter):
    tool = _tool(counter)
    with capture() as spans:
        tool()

    attrs = dict(spans[0].attributes or {})
    assert attrs[GenAI.OPERATION_NAME] == Operation.EXECUTE_TOOL == "execute_tool"
    assert GenAI.TOOL_NAME == "gen_ai.tool.name"
    assert attrs[GenAI.TOOL_NAME] == "lookup"
    assert SEMCONV_VERSION, "the pinned convention version must be declared"


# --- loop signature breaker ---


def test_breaker_opens_on_four_word_order_permutations():
    breaker = LoopSignatureBreaker()
    queries = [
        "refund policy for orders",
        "orders refund policy",
        "policy for refund orders",
        "for orders refund policy",
    ]
    states = [breaker.observe(q) for q in queries]
    assert states == [False, False, False, True]


def test_breaker_does_not_open_on_four_distinct_queries():
    breaker = LoopSignatureBreaker()
    queries = [
        "refund policy",
        "shipping times",
        "warranty coverage",
        "account closure steps",
    ]
    assert not any(breaker.observe(q) for q in queries)


def test_breaker_catches_an_alternating_two_phrase_loop():
    """A consecutive-only check would miss an A-B-A-B oscillation."""
    breaker = LoopSignatureBreaker()
    for query in ["refund policy orders", "orders refund policy"] * 2:
        state = breaker.observe(query)
    assert state


def test_text_similarity_is_word_order_invariant():
    assert text_similarity("a b c", "c b a") == 1.0
    assert text_similarity("a b c", "x y z") == 0.0
    assert 0.0 < text_similarity("a b c", "a b z") < 1.0


def test_breaker_resets():
    breaker = LoopSignatureBreaker()
    for q in ["a b c", "c b a", "b a c", "a c b"]:
        breaker.observe(q)
    assert breaker.opened
    breaker.reset()
    assert not breaker.opened


def test_a_window_below_two_is_rejected():
    with pytest.raises(ValueError):
        LoopSignatureBreaker(window=1)


# --- context and memory metrics ---


def test_record_context_observes_per_call_utilization():
    metrics = ContextMetrics()
    assert metrics.record_context(used_tokens=500, window_tokens=1000) == pytest.approx(0.5)
    assert metrics.record_context(used_tokens=900, window_tokens=1000) == pytest.approx(0.9)
    assert metrics.mean_utilization == pytest.approx(0.7)


def test_record_context_counts_truncations_by_dropped_kind():
    metrics = ContextMetrics()
    metrics.record_context(used_tokens=1000, window_tokens=1000, dropped={"retrieval": 3})
    metrics.record_context(used_tokens=1000, window_tokens=1000, dropped={"tool_results": 2})
    metrics.record_context(used_tokens=1000, window_tokens=1000, dropped={"retrieval": 1})

    assert metrics.truncations_for("retrieval") == 4
    assert metrics.truncations_for("tool_results") == 2
    assert metrics.truncations_for("history") == 0


def test_an_unknown_dropped_kind_is_rejected():
    with pytest.raises(ValueError):
        ContextMetrics().record_context(
            used_tokens=1, window_tokens=10, dropped={"nonsense": 1}
        )


def test_a_zero_window_is_rejected():
    with pytest.raises(ValueError):
        ContextMetrics().record_context(used_tokens=1, window_tokens=0)


@pytest.fixture()
def store():
    return LocalVectorStore(
        [
            MemoryItem("a", "refund policy", (1.0, 0.0, 0.0)),
            MemoryItem("b", "shipping times", (0.0, 1.0, 0.0)),
        ]
    )


def test_memory_retrieval_classifies_empty_miss_and_hit(store):
    metrics = MemoryMetrics()

    assert metrics.record_memory_retrieval([]) == "empty"
    assert metrics.record_memory_retrieval(store.search((1.0, 0.0, 0.0))) == "hit"
    assert metrics.record_memory_retrieval(
        store.search((0.0, 0.0, 1.0)), threshold=0.5
    ) == "miss"


def test_classification_at_the_threshold_boundary(store):
    """At the threshold is a hit, just below it is a miss."""
    metrics = MemoryMetrics()
    item = MemoryItem("x", "t", (1.0, 0.0, 0.0))
    exactly = [(item, DEFAULT_RELEVANCE_THRESHOLD)]
    just_below = [(item, DEFAULT_RELEVANCE_THRESHOLD - 1e-9)]

    assert metrics.record_memory_retrieval(exactly) == "hit"
    assert metrics.record_memory_retrieval(just_below) == "miss"


def test_an_empty_store_does_not_count_against_the_hit_rate(store):
    """A cold start is not a relevance problem."""
    metrics = MemoryMetrics()
    metrics.record_memory_retrieval([])
    metrics.record_memory_retrieval(store.search((1.0, 0.0, 0.0)))

    assert metrics.hit_rate() == pytest.approx(1.0)


# --- Exercise 16.3 reference solutions ---


def test_exercise_breakers_are_not_part_of_the_printed_listing():
    import chapters.ch16 as ch16

    for name in ("ElapsedTimeBreaker", "CostBreaker", "BudgetExceeded"):
        assert name not in ch16.__all__, f"{name} is Exercise 16.3, not Listing 16.1"


def test_elapsed_time_breaker_opens_past_its_budget():
    now = [0.0]
    breaker = ElapsedTimeBreaker(budget_seconds=5.0, clock=lambda: now[0])

    now[0] = 4.9
    breaker.check()

    now[0] = 5.1
    with pytest.raises(BudgetExceeded):
        breaker.check()


def test_cost_breaker_checks_before_the_call_not_after():
    """Checking afterwards overruns by exactly one call, every time."""
    breaker = CostBreaker(budget_usd=1.00)
    breaker.record(0.95)

    with pytest.raises(BudgetExceeded):
        breaker.check(next_call_usd=0.10)
    assert breaker.spent_usd == pytest.approx(0.95)

    breaker.check(next_call_usd=0.04)
