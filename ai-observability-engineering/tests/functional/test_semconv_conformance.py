"""Functional: no example may emit an attribute outside a declared namespace.

This is the repository-wide version of the Chapter 1 rule. It is the test
most likely to fail on a pull request, and that is the intent: an
accidental attribute is cheap to fix now and expensive to fix after two
teams have built dashboards on it.
"""

import pytest

from aiobs.semconv import CUSTOM_PREFIXES, OTEL_PREFIXES, classify
from aiobs.testing import ExampleHarness, genai_spans
from chapters.registry import all_examples

EXAMPLES = all_examples()
ALLOWED = OTEL_PREFIXES + CUSTOM_PREFIXES


@pytest.mark.parametrize("spec", EXAMPLES, ids=lambda s: s.id)
def test_no_unknown_attribute_namespaces(spec):
    result = ExampleHarness(require_semconv=False).run(spec.func, name=spec.id)
    offenders = {
        (span.name, key)
        for span in result.spans
        for key in dict(span.attributes or {})
        if classify(key) == "unknown"
    }
    assert not offenders, (
        f"{spec.id} emitted attributes outside {ALLOWED}: {sorted(offenders)}"
    )


@pytest.mark.parametrize("spec", EXAMPLES, ids=lambda s: s.id)
def test_no_legacy_llm_namespace_anywhere(spec):
    """The corrected Chapter 1 listing must not regress."""
    result = ExampleHarness(require_semconv=False).run(spec.func, name=spec.id)
    for span in result.spans:
        for key in dict(span.attributes or {}):
            assert not key.startswith("llm."), f"{spec.id}: {span.name} still uses {key}"


@pytest.mark.parametrize("spec", EXAMPLES, ids=lambda s: s.id)
def test_genai_spans_declare_a_provider(spec):
    from aiobs.semconv import GenAI

    result = ExampleHarness(require_semconv=False).run(spec.func, name=spec.id)
    for span in genai_spans(result.spans):
        attrs = dict(span.attributes or {})
        assert GenAI.PROVIDER_NAME in attrs, f"{spec.id}: {span.name} has no provider"


@pytest.mark.parametrize("spec", EXAMPLES, ids=lambda s: s.id)
def test_no_pii_reaches_telemetry(spec):
    """Chapter 12's rule, enforced across every example in the book."""
    result = ExampleHarness(require_semconv=False, require_no_pii=True).run(
        spec.func, name=spec.id
    )
    pii = [v for v in result.violations if "PII" in v]
    assert not pii, f"{spec.id}: {pii}"
