"""Testing harness for AI observability instrumentation.

Import assertions and the harness from here rather than from submodules;
the submodule layout is not part of the public interface.
"""

from .assertions import (
    SpanAssertionError,
    assert_attribute,
    assert_attribute_between,
    assert_cost_attributed,
    assert_error,
    assert_evaluated,
    assert_genai_span,
    assert_has_attributes,
    assert_llm_span,
    assert_no_pii,
    assert_ok,
    assert_parent_of,
    assert_same_trace,
    assert_semconv_compliant,
    assert_span_count,
    genai_spans,
    llm_spans,
    root_spans,
    spans_named,
    spans_with_attribute,
)
from .harness import ExampleHarness, HarnessResult, ObservabilityTestCase
from .scenarios import SCENARIOS, Scenario, get

__all__ = [
    "SCENARIOS",
    "ExampleHarness",
    "HarnessResult",
    "ObservabilityTestCase",
    "Scenario",
    "SpanAssertionError",
    "assert_attribute",
    "assert_attribute_between",
    "assert_cost_attributed",
    "assert_error",
    "assert_evaluated",
    "assert_genai_span",
    "assert_has_attributes",
    "assert_llm_span",
    "assert_no_pii",
    "assert_ok",
    "assert_parent_of",
    "assert_same_trace",
    "assert_semconv_compliant",
    "assert_span_count",
    "genai_spans",
    "get",
    "llm_spans",
    "root_spans",
    "spans_named",
    "spans_with_attribute",
]
