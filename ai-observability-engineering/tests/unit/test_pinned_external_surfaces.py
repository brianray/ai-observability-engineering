"""Cross-chapter: the external API surfaces the book's listings depend on.

Every listing that calls someone else's library is a listing that can
rot. These tests are the tripwire. They do not reach the network; they
check the installed packages against what the manuscript was written
against, so a dependency bump fails the build with the chapter named.

Verified 2026-09-21. See docs/PRINT_READINESS.md for what each result
means for the manuscript.
"""

from __future__ import annotations

import importlib.metadata as metadata

import pytest

from aiobs.semconv import (
    SEMCONV_PAGES,
    SEMCONV_SOURCE,
    SEMCONV_VERSION,
    GenAI,
    Operation,
)

# --- Chapter 4: the OpenAI streaming mechanism in Listing 4.1 ---

PINNED_OPENAI_VERSION = "1.109.1"


def test_openai_is_the_pinned_version():
    installed = metadata.version("openai")
    if installed != PINNED_OPENAI_VERSION:
        pytest.skip(
            f"openai {installed} installed, Listing 4.1 verified against "
            f"{PINNED_OPENAI_VERSION}; re-verify stream_options before print"
        )


def test_stream_options_include_usage_still_exists():
    """Listing 4.1's usage-on-stream mechanism."""
    from openai.types.chat import ChatCompletionStreamOptionsParam

    assert "include_usage" in ChatCompletionStreamOptionsParam.__annotations__, (
        "stream_options={'include_usage': True} is how Listing 4.1 gets token "
        "counts off a streamed response; if this is gone the listing is wrong"
    )


def test_chat_completions_still_accepts_stream_options():
    import inspect

    from openai.resources.chat import completions

    signature = inspect.signature(completions.Completions.create)
    assert "stream_options" in signature.parameters


# --- Chapters 4, 8, 10, 15, 16: the OTel GenAI conventions ---


def test_the_genai_conventions_source_is_the_repository_they_moved_to():
    assert SEMCONV_SOURCE.endswith("semantic-conventions-genai"), (
        "the GenAI conventions moved out of open-telemetry/semantic-conventions; "
        "the old path serves a 'Moved' stub"
    )
    assert SEMCONV_VERSION == "1.37.0"


def test_the_execute_tool_span_is_cited_on_the_model_spans_page():
    """The open question from Chapter 16's citation review.

    There is no separate tool-spans page. The execute-tool span is
    defined on the model spans page; the agent spans page only
    cross-references it.
    """
    assert SEMCONV_PAGES["execute_tool_span"].startswith("docs/gen-ai/gen-ai-spans.md")
    assert "agent" not in SEMCONV_PAGES["execute_tool_span"]


def test_the_operation_names_the_book_emits_are_the_spec_values():
    assert Operation.EXECUTE_TOOL == "execute_tool"
    assert Operation.INVOKE_AGENT == "invoke_agent"
    assert Operation.CHAT == "chat"


def test_the_tool_and_agent_attributes_the_book_emits_are_the_spec_names():
    assert GenAI.TOOL_NAME == "gen_ai.tool.name"
    assert GenAI.AGENT_NAME == "gen_ai.agent.name"


def test_tool_span_names_follow_the_spec_template():
    """The spec says span name SHOULD be `execute_tool {gen_ai.tool.name}`."""
    from aiobs import capture
    from chapters.ch16 import ObservableTool, ToolCounter

    tool = ObservableTool(name="flights", func=lambda: None, counter=ToolCounter())
    with capture() as spans:
        tool()
    assert spans[0].name == "execute_tool flights"


def test_agent_span_names_follow_the_spec_template():
    """`invoke_agent {gen_ai.agent.name}`."""
    from aiobs import capture
    from chapters.ch15 import run_pipeline

    with capture() as spans:
        run_pipeline(run_index=1)
    root = next(s for s in spans if s.name.startswith("invoke_agent"))
    assert root.name == "invoke_agent briefing_pipeline"
