"""Span assertions.

The premise of this module is that instrumentation is code, and untested
code rots. Every assertion here fails with a message that names the span,
the attribute, and what was found instead, because an assertion that says
only ``AssertionError: False is not true`` costs more time than it saves.

    from aiobs.testing import assert_llm_span, spans_named

    with capture() as spans:
        run_example()
    assert_llm_span(spans_named(spans, "chat mock-sonnet-1")[0])
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.trace import StatusCode

from ..semconv import REQUIRED_LLM_ATTRIBUTES, GenAI, classify


class SpanAssertionError(AssertionError):
    """Raised when a span does not meet an instrumentation contract."""


def _attrs(span: ReadableSpan) -> dict[str, Any]:
    return dict(span.attributes or {})


def _describe(span: ReadableSpan) -> str:
    return f"span {span.name!r}"


# --------------------------------------------------------------------- #
# Selection helpers
# --------------------------------------------------------------------- #

def spans_named(spans: Iterable[ReadableSpan], name: str) -> list[ReadableSpan]:
    return [s for s in spans if s.name == name]


def spans_with_attribute(
    spans: Iterable[ReadableSpan], key: str, value: Any = ...
) -> list[ReadableSpan]:
    out = []
    for span in spans:
        attrs = _attrs(span)
        if key in attrs and (value is ... or attrs[key] == value):
            out.append(span)
    return out


#: Operations that actually invoke a model, and therefore must carry a
#: model name and token counts. ``invoke_agent`` and ``execute_tool``
#: spans are GenAI spans too, but they have no model of their own, and
#: demanding one produces the fake ``model="n/a"`` attribute that makes a
#: trace harder to read rather than easier.
MODEL_INVOKING_OPERATIONS: tuple[str, ...] = ("chat", "text_completion", "embeddings")


def genai_spans(spans: Iterable[ReadableSpan]) -> list[ReadableSpan]:
    """Every span in the GenAI namespace, whatever the operation."""
    return spans_with_attribute(spans, GenAI.OPERATION_NAME)


def llm_spans(spans: Iterable[ReadableSpan]) -> list[ReadableSpan]:
    """GenAI spans that invoked a model and so must carry usage attributes."""
    return [
        s
        for s in genai_spans(spans)
        if dict(s.attributes or {}).get(GenAI.OPERATION_NAME) in MODEL_INVOKING_OPERATIONS
    ]


def root_spans(spans: Iterable[ReadableSpan]) -> list[ReadableSpan]:
    return [s for s in spans if s.parent is None]


# --------------------------------------------------------------------- #
# Structural assertions
# --------------------------------------------------------------------- #

def assert_span_count(spans: Sequence[ReadableSpan], expected: int) -> None:
    if len(spans) != expected:
        names = ", ".join(repr(s.name) for s in spans) or "none"
        raise SpanAssertionError(
            f"expected {expected} span(s), found {len(spans)}: {names}"
        )


def assert_has_attributes(span: ReadableSpan, *keys: str) -> None:
    attrs = _attrs(span)
    missing = [k for k in keys if k not in attrs]
    if missing:
        raise SpanAssertionError(
            f"{_describe(span)} is missing {missing}; has {sorted(attrs)}"
        )


def assert_attribute(span: ReadableSpan, key: str, expected: Any) -> None:
    attrs = _attrs(span)
    if key not in attrs:
        raise SpanAssertionError(f"{_describe(span)} has no attribute {key!r}")
    if attrs[key] != expected:
        raise SpanAssertionError(
            f"{_describe(span)} attribute {key!r}: expected {expected!r}, got {attrs[key]!r}"
        )


def assert_attribute_between(
    span: ReadableSpan, key: str, low: float, high: float
) -> None:
    attrs = _attrs(span)
    if key not in attrs:
        raise SpanAssertionError(f"{_describe(span)} has no attribute {key!r}")
    value = attrs[key]
    if not low <= value <= high:
        raise SpanAssertionError(
            f"{_describe(span)} attribute {key!r}: {value} outside [{low}, {high}]"
        )


def assert_ok(span: ReadableSpan) -> None:
    if span.status.status_code is StatusCode.ERROR:
        raise SpanAssertionError(
            f"{_describe(span)} has ERROR status: {span.status.description}"
        )


def assert_error(span: ReadableSpan) -> None:
    if span.status.status_code is not StatusCode.ERROR:
        raise SpanAssertionError(
            f"{_describe(span)} expected ERROR status, got {span.status.status_code}"
        )


def assert_parent_of(parent: ReadableSpan, child: ReadableSpan) -> None:
    if child.parent is None:
        raise SpanAssertionError(f"{_describe(child)} has no parent")
    if child.parent.span_id != parent.context.span_id:
        raise SpanAssertionError(
            f"{_describe(child)} is not a child of {_describe(parent)}"
        )


def assert_same_trace(spans: Sequence[ReadableSpan]) -> None:
    """Every span belongs to one trace.

    The failure this catches is context loss across an async boundary or
    a thread pool, which produces orphaned traces that look fine in
    isolation and are useless for debugging a request end to end.
    """
    trace_ids = {s.context.trace_id for s in spans}
    if len(trace_ids) > 1:
        raise SpanAssertionError(
            f"spans span {len(trace_ids)} traces; context propagation is broken"
        )


# --------------------------------------------------------------------- #
# Contract assertions
# --------------------------------------------------------------------- #

def assert_llm_span(span: ReadableSpan) -> None:
    """The minimum contract for a model-invoking span in this book.

    Agent and tool spans are checked by :func:`assert_genai_span`
    instead; they are legitimately modelless.
    """
    attrs = _attrs(span)
    operation = attrs.get(GenAI.OPERATION_NAME)
    if operation not in MODEL_INVOKING_OPERATIONS:
        raise SpanAssertionError(
            f"{_describe(span)} has operation {operation!r}; "
            f"assert_llm_span applies to {MODEL_INVOKING_OPERATIONS}"
        )
    assert_has_attributes(span, *REQUIRED_LLM_ATTRIBUTES)
    attrs = _attrs(span)
    for key in (GenAI.USAGE_INPUT_TOKENS, GenAI.USAGE_OUTPUT_TOKENS):
        if not isinstance(attrs[key], int) or attrs[key] < 0:
            raise SpanAssertionError(
                f"{_describe(span)} attribute {key!r} must be a non-negative int, "
                f"got {attrs[key]!r}"
            )


def assert_genai_span(span: ReadableSpan) -> None:
    """The contract every GenAI span meets, model-invoking or not."""
    assert_has_attributes(span, GenAI.OPERATION_NAME, GenAI.PROVIDER_NAME)
    operation = _attrs(span)[GenAI.OPERATION_NAME]
    if operation in MODEL_INVOKING_OPERATIONS:
        assert_llm_span(span)


def assert_semconv_compliant(span: ReadableSpan, allow_unknown: bool = False) -> None:
    """Every attribute is either standardized or deliberately namespaced.

    Chapter 1's rule in executable form. Attributes that are neither are
    almost always an accident, and they are the reason two teams in the
    same company end up unable to query each other's telemetry.
    """
    unknown = [
        key
        for key in _attrs(span)
        if classify(key) == "unknown" and not key.startswith(("service.", "aiobs."))
    ]
    if unknown and not allow_unknown:
        raise SpanAssertionError(
            f"{_describe(span)} carries non-namespaced attributes {sorted(unknown)}; "
            "use gen_ai.* for standardized fields or a prefix you own for the rest"
        )


def assert_no_pii(span: ReadableSpan, patterns: Sequence[str] | None = None) -> None:
    """No span attribute value looks like PII.

    Chapter 12's rule: telemetry records that something happened, not the
    payload it happened to. This is the test that keeps a debugging
    session from becoming a data-protection incident.
    """
    import re

    default = [
        r"[\w.+-]+@[\w-]+\.[\w.]{2,}",
        r"\b\d{3}-\d{2}-\d{4}\b",
        r"\b(?:\d[ -]*?){13,16}\b",
    ]
    compiled = [re.compile(p) for p in (patterns or default)]
    for key, value in _attrs(span).items():
        if not isinstance(value, str):
            continue
        for pattern in compiled:
            if pattern.search(value):
                raise SpanAssertionError(
                    f"{_describe(span)} attribute {key!r} looks like PII "
                    f"(pattern {pattern.pattern!r})"
                )


def assert_cost_attributed(span: ReadableSpan) -> None:
    """Cost is present and assigned to something a finance partner recognizes."""
    from ..semconv import Aiobs

    assert_has_attributes(span, Aiobs.COST_USD, Aiobs.COST_TENANT)
    attrs = _attrs(span)
    if attrs[Aiobs.COST_TENANT] == "unattributed":
        raise SpanAssertionError(
            f"{_describe(span)} records cost but leaves it unattributed; "
            "unattributed spend is the ROI failure mode of Part III"
        )


def assert_evaluated(span: ReadableSpan, *, max_hallucination: float = 1.0) -> None:
    """The span carries eval scores, with the set version recorded."""
    from ..semconv import Eval

    assert_has_attributes(span, Eval.HALLUCINATION_SCORE, Eval.GROUNDEDNESS_SCORE)
    attrs = _attrs(span)
    if attrs[Eval.HALLUCINATION_SCORE] > max_hallucination:
        raise SpanAssertionError(
            f"{_describe(span)} hallucination score {attrs[Eval.HALLUCINATION_SCORE]} "
            f"exceeds {max_hallucination}"
        )
