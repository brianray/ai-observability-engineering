"""Chapter 10 companion files."""

from .guardrails import (
    ACTION_ALLOW,
    ACTION_BLOCK,
    ACTION_FLAG,
    BLOCK_THRESHOLD,
    GuardrailDecision,
    guarded_call,
    input_guardrail,
    output_guardrail,
)
from .injection_detector import (
    EVENT_FIELDS,
    INJECTION_PATTERNS,
    InjectionFinding,
    detect_injection,
    emit_injection_event,
    text_fingerprint,
)
from .redteam import CASES_PATH, load_cases, run_suite

__all__ = [
    "ACTION_ALLOW",
    "ACTION_BLOCK",
    "ACTION_FLAG",
    "BLOCK_THRESHOLD",
    "CASES_PATH",
    "EVENT_FIELDS",
    "INJECTION_PATTERNS",
    "GuardrailDecision",
    "InjectionFinding",
    "detect_injection",
    "emit_injection_event",
    "guarded_call",
    "input_guardrail",
    "load_cases",
    "output_guardrail",
    "run_suite",
    "text_fingerprint",
]
