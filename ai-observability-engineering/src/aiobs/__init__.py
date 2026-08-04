"""AI Observability Engineering: the companion framework.

Reference implementation for *AI Observability Engineering: Operating
Intelligent Systems in Production* (Pearson Addison-Wesley).

The framework is organized around the two structures the book uses
throughout: the four pillars from Chapter 1 (Performance, ROI, Risk,
Responsibility) and the five observable layers from Chapter 2.

Quick start::

    from aiobs import MockProvider, llm_span, capture
    from aiobs.testing import assert_llm_span

    with capture() as spans:
        with llm_span(provider="mock", model="mock-sonnet-1") as span:
            reply = MockProvider().chat("hello")
    assert_llm_span(spans[0])
"""

from .agents import AgentRun, MastFailureMode
from .cost import CostLedger, cost_per_outcome, price_call, roi
from .drift import detect as detect_drift
from .evals import default_suite
from .instrument import (
    llm_span,
    observe,
    set_cost_attributes,
    set_eval_attributes,
    set_llm_attributes,
)
from .pillars import Layer, Pillar, Scope
from .providers import ChatResponse, FailureMode, LLMProvider, MockProvider
from .risk import OwaspLLM, scan
from .semconv import SEMCONV_VERSION, Aiobs, Eval, GenAI, Operation
from .telemetry import capture, configure, get_finished_spans, get_tracer, reset

__version__ = "0.1.0"

__all__ = [
    "SEMCONV_VERSION",
    "AgentRun",
    "Aiobs",
    "ChatResponse",
    "CostLedger",
    "Eval",
    "FailureMode",
    "GenAI",
    "LLMProvider",
    "Layer",
    "MastFailureMode",
    "MockProvider",
    "Operation",
    "OwaspLLM",
    "Pillar",
    "Scope",
    "__version__",
    "capture",
    "configure",
    "cost_per_outcome",
    "default_suite",
    "detect_drift",
    "get_finished_spans",
    "get_tracer",
    "llm_span",
    "observe",
    "price_call",
    "reset",
    "roi",
    "scan",
    "set_cost_attributes",
    "set_eval_attributes",
    "set_llm_attributes",
]
