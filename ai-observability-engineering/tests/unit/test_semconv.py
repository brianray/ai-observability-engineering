"""Unit tests: attribute namespaces."""

import pytest

from aiobs.semconv import (
    REQUIRED_LLM_ATTRIBUTES,
    SEMCONV_VERSION,
    Aiobs,
    Eval,
    GenAI,
    classify,
    is_custom,
    is_genai,
    is_standard,
)


def test_genai_attributes_use_the_reserved_prefix():
    for name in dir(GenAI):
        if not name.startswith("_"):
            assert getattr(GenAI, name).startswith("gen_ai.")


def test_eval_attributes_are_not_in_the_standard_namespace():
    """The eval namespace is this book's invention and must stay marked."""
    for name in ("HALLUCINATION_SCORE", "GROUNDEDNESS_SCORE", "RELEVANCE_SCORE"):
        attribute = getattr(Eval, name)
        assert attribute.startswith("eval.")
        assert not is_genai(attribute)
        assert is_custom(attribute)


def test_aiobs_attributes_are_custom():
    assert is_custom(Aiobs.COST_USD)
    assert not is_genai(Aiobs.COST_USD)


@pytest.mark.parametrize(
    ("attribute", "expected"),
    [
        ("gen_ai.request.model", "standard"),
        ("http.response.status_code", "standard"),
        ("service.name", "standard"),
        ("eval.groundedness_score", "custom"),
        ("aiobs.cost.usd", "custom"),
        ("llm.model", "unknown"),
        ("my_random_attribute", "unknown"),
    ],
)
def test_classify(attribute, expected):
    assert classify(attribute) == expected


def test_legacy_llm_prefix_is_not_standard():
    """Guards the Chapter 1 correction: llm.* was never a convention."""
    assert not is_standard("llm.prompt_tokens")
    assert classify("llm.prompt_tokens") == "unknown"


def test_required_llm_attributes_are_all_genai():
    assert all(a.startswith("gen_ai.") for a in REQUIRED_LLM_ATTRIBUTES)
    assert GenAI.USAGE_INPUT_TOKENS in REQUIRED_LLM_ATTRIBUTES


def test_semconv_version_is_pinned():
    """A moving specification needs a pinned version, not a live reference."""
    assert SEMCONV_VERSION.count(".") == 2
