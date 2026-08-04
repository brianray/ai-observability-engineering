"""Unit tests for the harness itself.

The harness is the thing every chapter's tests depend on, so it gets the
most adversarial tests in the repository. A harness that reports PASS on
broken instrumentation is worse than no harness.
"""

import pytest

from aiobs import Layer, Pillar, capture, get_tracer, llm_span, observe
from aiobs.instrument import set_cost_attributes, set_llm_attributes
from aiobs.semconv import Aiobs, Eval, GenAI, Operation
from aiobs.testing import (
    ExampleHarness,
    ObservabilityTestCase,
    SpanAssertionError,
    assert_cost_attributed,
    assert_evaluated,
    assert_genai_span,
    assert_llm_span,
    assert_no_pii,
    assert_same_trace,
    assert_semconv_compliant,
    assert_span_count,
    genai_spans,
    llm_spans,
    spans_named,
)


def _good_example():
    with llm_span(provider="mock", model="mock-sonnet-1", pillar=Pillar.PERFORMANCE) as span:
        set_llm_attributes(
            span, provider="mock", model="mock-sonnet-1", input_tokens=10, output_tokens=5
        )


def _example_with_legacy_names():
    with get_tracer(__name__).start_as_current_span("chat") as span:
        span.set_attribute("llm.model", "mock-sonnet-1")
        span.set_attribute("llm.prompt_tokens", 10)


def _example_leaking_pii():
    with llm_span(provider="mock", model="mock-sonnet-1") as span:
        set_llm_attributes(
            span, provider="mock", model="mock-sonnet-1", input_tokens=1, output_tokens=1
        )
        span.set_attribute("aiobs.debug.prompt", "contact bob@example.com about it")


def _example_emitting_nothing():
    return 42


def _example_that_raises():
    raise RuntimeError("boom")


# --------------------------------------------------------------------- #
# ExampleHarness
# --------------------------------------------------------------------- #

def test_harness_passes_a_correctly_instrumented_example():
    result = ExampleHarness().run(_good_example)
    assert result.ok
    assert result.llm_span_count == 1
    assert result.total_tokens == 15


def test_harness_rejects_the_legacy_llm_namespace():
    """The Chapter 1 correction, enforced. llm.* must not pass."""
    result = ExampleHarness().run(_example_with_legacy_names)
    assert not result.ok
    assert any("non-namespaced" in v for v in result.violations)


def test_harness_rejects_pii_in_span_attributes():
    result = ExampleHarness().run(_example_leaking_pii)
    assert not result.ok
    assert any("PII" in v for v in result.violations)


def test_harness_flags_an_example_that_emits_no_spans():
    result = ExampleHarness().run(_example_emitting_nothing)
    assert not result.ok
    assert result.violations == ["example emitted no spans"]


def test_harness_records_an_exception_without_propagating_it():
    result = ExampleHarness().run(_example_that_raises)
    assert isinstance(result.error, RuntimeError)
    assert not result.ok


def test_expect_error_inverts_the_pass_condition():
    result = ExampleHarness(require_semconv=False).run(
        _example_that_raises, expect_error=True
    )
    assert result.error is None
    assert result.violations == ["example emitted no spans"]


def test_expect_error_fails_when_nothing_raises():
    result = ExampleHarness().run(_good_example, expect_error=True)
    assert "expected an exception" in result.violations[0]


def test_lenient_mode_skips_convention_enforcement():
    result = ExampleHarness(require_semconv=False, require_no_pii=False).run(
        _example_with_legacy_names
    )
    assert result.ok


def test_harness_reports_pillar_and_layer_coverage():
    result = ExampleHarness().run(_good_example)
    assert result.pillars_covered() == {Pillar.PERFORMANCE.value}
    assert result.layers_covered() == {Layer.MODEL_AND_INFERENCE.value}


# --------------------------------------------------------------------- #
# Assertions
# --------------------------------------------------------------------- #

def test_assert_llm_span_requires_token_counts():
    with capture() as spans, get_tracer(__name__).start_as_current_span("chat") as span:
        span.set_attribute(GenAI.OPERATION_NAME, Operation.CHAT)
        span.set_attribute(GenAI.PROVIDER_NAME, "mock")
        span.set_attribute(GenAI.REQUEST_MODEL, "mock-sonnet-1")
    with pytest.raises(SpanAssertionError, match="missing"):
        assert_llm_span(spans[0])


def test_assert_llm_span_rejects_string_token_counts():
    with capture() as spans, get_tracer(__name__).start_as_current_span("chat") as span:
        span.set_attribute(GenAI.OPERATION_NAME, Operation.CHAT)
        span.set_attribute(GenAI.PROVIDER_NAME, "mock")
        span.set_attribute(GenAI.REQUEST_MODEL, "mock-sonnet-1")
        span.set_attribute(GenAI.USAGE_INPUT_TOKENS, "512")
        span.set_attribute(GenAI.USAGE_OUTPUT_TOKENS, 128)
    with pytest.raises(SpanAssertionError, match="non-negative int"):
        assert_llm_span(spans[0])


def test_tool_spans_are_genai_spans_without_a_model():
    """An execute_tool span has no model. Demanding one produces fake data."""
    with capture() as spans:
        with get_tracer(__name__).start_as_current_span("execute_tool lookup") as span:
            span.set_attribute(GenAI.OPERATION_NAME, Operation.EXECUTE_TOOL)
            span.set_attribute(GenAI.PROVIDER_NAME, "internal")
            span.set_attribute(GenAI.TOOL_NAME, "lookup")
    assert_genai_span(spans[0])
    assert genai_spans(spans) == spans
    assert llm_spans(spans) == []


def test_assert_same_trace_catches_broken_context_propagation():
    with capture() as spans:
        with get_tracer(__name__).start_as_current_span("a"):
            pass
        with get_tracer(__name__).start_as_current_span("b"):
            pass
    with pytest.raises(SpanAssertionError, match="context propagation"):
        assert_same_trace(spans)


def test_assert_same_trace_passes_for_a_nested_trace():
    with capture() as spans, get_tracer(__name__).start_as_current_span("parent"):
        with get_tracer(__name__).start_as_current_span("child"):
            pass
    assert_same_trace(spans)


def test_assert_cost_attributed_rejects_unattributed_spend():
    with capture() as spans, get_tracer(__name__).start_as_current_span("chat") as span:
        set_cost_attributes(span, 0.01)
    with pytest.raises(SpanAssertionError, match="unattributed"):
        assert_cost_attributed(spans[0])


def test_assert_evaluated_enforces_a_hallucination_ceiling():
    with capture() as spans, get_tracer(__name__).start_as_current_span("chat") as span:
        span.set_attribute(Eval.HALLUCINATION_SCORE, 0.9)
        span.set_attribute(Eval.GROUNDEDNESS_SCORE, 0.1)
    with pytest.raises(SpanAssertionError, match="exceeds"):
        assert_evaluated(spans[0], max_hallucination=0.2)


def test_assert_span_count_message_lists_what_it_found():
    with capture() as spans, get_tracer(__name__).start_as_current_span("only_one"):
        pass
    with pytest.raises(SpanAssertionError, match="only_one"):
        assert_span_count(spans, 3)


def test_observe_decorator_tags_pillar_and_layer():
    @observe(pillar=Pillar.RISK, layer=Layer.DATA_AND_RETRIEVAL)
    def retrieve():
        return "documents"

    with capture() as spans:
        retrieve()
    attrs = dict(spans[0].attributes)
    assert attrs[Aiobs.PILLAR] == Pillar.RISK.value
    assert attrs[Aiobs.LAYER] == Layer.DATA_AND_RETRIEVAL.value


def test_observe_decorator_records_exceptions_and_reraises():
    @observe(pillar=Pillar.RISK, layer=Layer.INFRASTRUCTURE)
    def explode():
        raise ValueError("nope")

    with capture() as spans, pytest.raises(ValueError):
        explode()
    assert spans[0].status.status_code.name == "ERROR"


def test_llm_span_marks_status_error_on_exception():
    with capture() as spans, pytest.raises(RuntimeError):
        with llm_span(provider="mock", model="mock-sonnet-1"):
            raise RuntimeError("upstream 503")
    assert spans[0].status.status_code.name == "ERROR"


def test_assert_no_pii_ignores_non_string_attributes():
    with capture() as spans, get_tracer(__name__).start_as_current_span("chat") as span:
        span.set_attribute("aiobs.count", 1234567890123456)
    assert_no_pii(spans[0])


def test_semconv_compliance_accepts_declared_namespaces():
    with capture() as spans, get_tracer(__name__).start_as_current_span("chat") as span:
        span.set_attribute("gen_ai.request.model", "m")
        span.set_attribute("http.response.status_code", 200)
        span.set_attribute("eval.groundedness_score", 0.9)
        span.set_attribute("aiobs.pillar", "risk")
    assert_semconv_compliant(spans[0])


def test_spans_named_helper():
    with capture() as spans, get_tracer(__name__).start_as_current_span("target"):
        pass
    assert len(spans_named(spans, "target")) == 1
    assert spans_named(spans, "absent") == []


# --------------------------------------------------------------------- #
# ObservabilityTestCase
# --------------------------------------------------------------------- #

class TestObservabilityTestCase(ObservabilityTestCase):
    """The unittest-style entry point, exercising itself."""

    def test_capture_and_assert(self):
        with self.capture_spans():
            _good_example()
        self.assertSpanCount(1)
        self.assertLLMSpanCount(1)
        self.assertAllSpansCompliant()
        self.assertAllLLMSpansValid()
        self.assertNoPII()
        self.assertSingleTrace()
        self.assertPillarCovered(Pillar.PERFORMANCE.value)

    def test_span_named_failure_message_lists_candidates(self):
        with self.capture_spans():
            _good_example()
        with self.assertRaises(AssertionError) as ctx:
            self.assertSpanNamed("does_not_exist")
        assert "chat mock-sonnet-1" in str(ctx.exception)
