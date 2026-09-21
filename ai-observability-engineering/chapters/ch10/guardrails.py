"""Input and output guardrails, and the span attributes that audit them (Listing 10.2).

A guardrail decision is a three-way outcome, not a boolean: block the
call, let it through but flag it for review, or allow it. The chapter's
argument is that all three have to reach the span, including ``allow``.
A guardrail that records only its blocks gives you a numerator with no
denominator, so you can never answer "what fraction of traffic did this
thing stop this week" or notice the day it silently stopped firing.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from aiobs import Aiobs, get_logger, get_tracer
from aiobs.risk import detect_system_prompt_leak

from .injection_detector import detect_injection, emit_injection_event

log = get_logger(__name__)

#: At or above this score the call is blocked; below it but non-zero the
#: call proceeds and is flagged. Tuned for the book's fixtures, not for
#: your traffic: pick this from your own false-positive budget.
BLOCK_THRESHOLD: float = 0.75

ACTION_BLOCK = "block"
ACTION_FLAG = "flag"
ACTION_ALLOW = "allow"


@dataclass(frozen=True)
class GuardrailDecision:
    action: str
    score: float
    reason: str

    @property
    def blocked(self) -> bool:
        return self.action == ACTION_BLOCK


def input_guardrail(text: str, *, threshold: float = BLOCK_THRESHOLD) -> GuardrailDecision:
    """Block above ``threshold``, flag anything else that fired, else allow."""
    finding = detect_injection(text)
    if not finding.triggered:
        return GuardrailDecision(ACTION_ALLOW, 0.0, "no_pattern_matched")

    emit_injection_event(finding, text)
    if finding.score >= threshold:
        return GuardrailDecision(ACTION_BLOCK, finding.score, "injection_above_threshold")
    return GuardrailDecision(ACTION_FLAG, finding.score, "injection_below_threshold")


def output_guardrail(output: str, system_prompt: str) -> GuardrailDecision:
    """Catch the system prompt coming back out in the completion."""
    report = detect_system_prompt_leak(output, system_prompt)
    if not report.triggered:
        return GuardrailDecision(ACTION_ALLOW, 0.0, "no_leak_detected")
    return GuardrailDecision(ACTION_BLOCK, 0.9, "system_prompt_leak")


def guarded_call(
    prompt: str,
    *,
    system_prompt: str,
    call: Callable[[str], str],
    threshold: float = BLOCK_THRESHOLD,
    span_name: str = "guarded_chat",
) -> dict[str, Any]:
    """Run ``call`` behind both guardrails, recording every decision.

    Both ``aiobs.guardrail.input.action`` and
    ``aiobs.guardrail.output.action`` are set on every path. On a blocked
    input the output guardrail never runs, so its action is recorded as
    ``not_evaluated`` rather than left absent: an absent attribute and a
    guardrail that passed are indistinguishable in a query, which is
    exactly the ambiguity an auditor will find.
    """
    tracer = get_tracer(__name__)
    with tracer.start_as_current_span(span_name) as span:
        decision = input_guardrail(prompt, threshold=threshold)
        span.set_attribute(Aiobs.GUARDRAIL_INPUT_ACTION, decision.action)
        span.set_attribute(Aiobs.GUARDRAIL_SCORE, decision.score)

        if decision.blocked:
            span.set_attribute(Aiobs.GUARDRAIL_OUTPUT_ACTION, "not_evaluated")
            span.set_attribute(Aiobs.RISK_INJECTION_DETECTED, True)
            return {
                "input_action": decision.action,
                "output_action": "not_evaluated",
                "completion": None,
                "blocked": True,
            }

        span.set_attribute(Aiobs.RISK_INJECTION_DETECTED, decision.action == ACTION_FLAG)
        completion = call(prompt)
        out_decision = output_guardrail(completion, system_prompt)
        span.set_attribute(Aiobs.GUARDRAIL_OUTPUT_ACTION, out_decision.action)

        return {
            "input_action": decision.action,
            "output_action": out_decision.action,
            "completion": None if out_decision.blocked else completion,
            "blocked": out_decision.blocked,
        }
