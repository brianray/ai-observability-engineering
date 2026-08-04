"""The observability test harness.

Two entry points, depending on how you like to write tests.

``ObservabilityTestCase``
    A ``unittest.TestCase`` subclass that configures the tracer, captures
    spans, and exposes the assertions as methods.

``ExampleHarness``
    A plain object for pytest users and for the simulator, which runs
    every example in the book through the same checks.

Both enforce the same contract, so a chapter example that passes one
passes the other.
"""

from __future__ import annotations

import unittest
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from opentelemetry.sdk.trace import ReadableSpan

from ..semconv import Aiobs, GenAI
from ..telemetry import configure, get_finished_spans, reset
from . import assertions as checks


@dataclass
class HarnessResult:
    """What running one example produced."""

    name: str
    spans: list[ReadableSpan] = field(default_factory=list)
    returned: Any = None
    error: BaseException | None = None
    violations: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.error is None and not self.violations

    @property
    def llm_span_count(self) -> int:
        return len(checks.llm_spans(self.spans))

    @property
    def total_tokens(self) -> int:
        total = 0
        for span in checks.llm_spans(self.spans):
            attrs = dict(span.attributes or {})
            for key in (GenAI.USAGE_INPUT_TOKENS, GenAI.USAGE_OUTPUT_TOKENS):
                value = attrs.get(key, 0)
                if isinstance(value, (int, float)):
                    total += int(value)
        return total

    @property
    def total_cost_usd(self) -> float:
        total = 0.0
        for span in self.spans:
            value = dict(span.attributes or {}).get(Aiobs.COST_USD, 0.0)
            if isinstance(value, (int, float)):
                total += float(value)
        return round(total, 6)

    def pillars_covered(self) -> set[str]:
        return {
            str(dict(s.attributes or {})[Aiobs.PILLAR])
            for s in self.spans
            if Aiobs.PILLAR in dict(s.attributes or {})
        }

    def layers_covered(self) -> set[str]:
        return {
            str(dict(s.attributes or {})[Aiobs.LAYER])
            for s in self.spans
            if Aiobs.LAYER in dict(s.attributes or {})
        }


class ExampleHarness:
    """Runs a callable, captures its spans, and applies the contract checks.

    ``expect_error=True`` inverts the pass condition, so an example whose
    whole point is to demonstrate a failure can still be a green test.
    """

    def __init__(
        self,
        *,
        service_name: str = "aiobs-harness",
        require_semconv: bool = True,
        require_no_pii: bool = True,
        allow_unknown_attributes: bool = False,
    ) -> None:
        self.service_name = service_name
        self.require_semconv = require_semconv
        self.require_no_pii = require_no_pii
        self.allow_unknown_attributes = allow_unknown_attributes

    def run(
        self,
        func: Callable[..., Any],
        *args: Any,
        name: str | None = None,
        expect_error: bool = False,
        **kwargs: Any,
    ) -> HarnessResult:
        configure(service_name=self.service_name, exporter="memory", force=True)
        reset()

        label = name or str(getattr(func, "__name__", "anonymous"))
        result = HarnessResult(name=label)
        try:
            result.returned = func(*args, **kwargs)
        except BaseException as exc:
            if not expect_error:
                result.error = exc
        else:
            if expect_error:
                result.violations.append("expected an exception, none raised")

        result.spans = list(get_finished_spans())
        result.violations.extend(self._check(result.spans))
        return result

    def _check(self, spans: Sequence[ReadableSpan]) -> list[str]:
        violations: list[str] = []
        if not spans:
            return ["example emitted no spans"]

        for span in spans:
            if self.require_semconv:
                try:
                    checks.assert_semconv_compliant(span, self.allow_unknown_attributes)
                except checks.SpanAssertionError as exc:
                    violations.append(str(exc))
            if self.require_no_pii:
                try:
                    checks.assert_no_pii(span)
                except checks.SpanAssertionError as exc:
                    violations.append(str(exc))

        for span in checks.genai_spans(spans):
            try:
                checks.assert_genai_span(span)
            except checks.SpanAssertionError as exc:
                violations.append(str(exc))

        return violations


class ObservabilityTestCase(unittest.TestCase):
    """unittest base class with span capture and the assertion set attached.

        class TestMyPipeline(ObservabilityTestCase):
            def test_emits_llm_span(self):
                with self.capture_spans():
                    my_pipeline("hello")
                self.assertLLMSpanCount(1)
                self.assertAllSpansCompliant()
    """

    service_name = "aiobs-testcase"

    def setUp(self) -> None:
        super().setUp()
        configure(service_name=self.service_name, exporter="memory", force=True)
        reset()
        self._spans: list[ReadableSpan] = []

    # -- capture -------------------------------------------------------
    class _Capture:
        def __init__(self, case: ObservabilityTestCase) -> None:
            self.case = case

        def __enter__(self) -> ObservabilityTestCase._Capture:
            reset()
            return self

        def __exit__(self, *exc: Any) -> None:
            self.case._spans = list(get_finished_spans())

    def capture_spans(self) -> ObservabilityTestCase._Capture:
        return self._Capture(self)

    @property
    def spans(self) -> list[ReadableSpan]:
        if not self._spans:
            self._spans = list(get_finished_spans())
        return self._spans

    # -- assertions ----------------------------------------------------
    def assertSpanCount(self, expected: int) -> None:  # noqa: N802
        checks.assert_span_count(self.spans, expected)

    def assertLLMSpanCount(self, expected: int) -> None:  # noqa: N802
        checks.assert_span_count(checks.llm_spans(self.spans), expected)

    def assertSpanNamed(self, name: str) -> ReadableSpan:  # noqa: N802
        found = checks.spans_named(self.spans, name)
        if not found:
            names = sorted({s.name for s in self.spans})
            raise AssertionError(f"no span named {name!r}; saw {names}")
        return found[0]

    def assertAllSpansCompliant(self, allow_unknown: bool = False) -> None:  # noqa: N802
        for span in self.spans:
            checks.assert_semconv_compliant(span, allow_unknown)

    def assertAllLLMSpansValid(self) -> None:  # noqa: N802
        for span in checks.llm_spans(self.spans):
            checks.assert_llm_span(span)

    def assertNoPII(self) -> None:  # noqa: N802
        for span in self.spans:
            checks.assert_no_pii(span)

    def assertSingleTrace(self) -> None:  # noqa: N802
        checks.assert_same_trace(self.spans)

    def assertPillarCovered(self, pillar: str) -> None:  # noqa: N802
        covered = {
            dict(s.attributes or {}).get(Aiobs.PILLAR) for s in self.spans
        }
        if pillar not in covered:
            raise AssertionError(f"no span tagged with pillar {pillar!r}; saw {covered}")
