"""Prompt-injection detection that emits a signal, not the payload (Listing 10.1).

The detector is deliberately unimpressive. It is a pattern list, and a
pattern list catches the lazy attacker and nobody else. It earns its place
in the book because of what it does *after* it fires: it emits a
structured event with a stable set of fields, correlated to the trace,
carrying no attacker-supplied text.

That last property is the whole point. A detector that logs what it
caught turns your log store into a copy of the attack corpus, readable by
everyone with dashboard access.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from aiobs import get_logger
from aiobs.risk import OwaspLLM, Severity

log = get_logger(__name__)

#: (name, pattern, severity). ``name`` is the label that reaches
#: telemetry; the pattern never does.
INJECTION_PATTERNS: tuple[tuple[str, str, Severity], ...] = (
    (
        "override_instructions",
        r"\bignore\s+(?:all\s+|any\s+)?(?:previous|prior|above|earlier)\s+instructions?\b",
        Severity.HIGH,
    ),
    (
        "disregard_system_prompt",
        r"\bdisregard\s+(?:your|the)\s+(?:system\s+)?prompt\b",
        Severity.HIGH,
    ),
    (
        "mode_switch",
        r"\byou\s+are\s+now\s+(?:in\s+)?(?:developer|admin|god|dan)\s+mode\b",
        Severity.HIGH,
    ),
    (
        "reveal_instructions",
        r"\b(?:reveal|print|output|show)\s+(?:me\s+)?(?:your|the)\s+(?:system\s+)?(?:prompt|instructions)\b",
        Severity.HIGH,
    ),
    (
        "repeat_context",
        r"\brepeat\s+(?:everything|the\s+text|all\s+text)\s+above\b",
        Severity.MEDIUM,
    ),
    (
        "role_reassignment",
        r"\bpretend\s+(?:you\s+are|to\s+be)\s+(?:an?\s+)?(?:unrestricted|uncensored|jailbroken)\b",
        Severity.MEDIUM,
    ),
)

_SEVERITY_SCORE: dict[Severity, float] = {
    Severity.NONE: 0.0,
    Severity.LOW: 0.25,
    Severity.MEDIUM: 0.55,
    Severity.HIGH: 0.90,
}


@dataclass(frozen=True)
class InjectionFinding:
    """What fired, and how confident. Never what the attacker wrote."""

    matched_patterns: tuple[str, ...]
    severity: Severity
    score: float
    owasp_id: str = OwaspLLM.PROMPT_INJECTION.value

    @property
    def triggered(self) -> bool:
        return bool(self.matched_patterns)


def text_fingerprint(text: str) -> str:
    """A stable reference to a payload that is not the payload.

    Correlating repeat attempts needs an identifier, and the identifier
    has to survive being written to a log that a wide audience can read.
    A truncated digest does both.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def detect_injection(text: str) -> InjectionFinding:
    """Score ``text`` against ``INJECTION_PATTERNS``."""
    matched = tuple(
        name
        for name, pattern, _ in INJECTION_PATTERNS
        if re.search(pattern, text, re.IGNORECASE)
    )
    if not matched:
        return InjectionFinding((), Severity.NONE, 0.0)

    by_name = {name: severity for name, _, severity in INJECTION_PATTERNS}
    order = [Severity.NONE, Severity.LOW, Severity.MEDIUM, Severity.HIGH]
    severity = max((by_name[n] for n in matched), key=order.index)
    return InjectionFinding(matched, severity, _SEVERITY_SCORE[severity])


#: The fields every injection event carries. Asserted by the test suite
#: so a future edit cannot quietly drop one and break every saved query.
EVENT_FIELDS: tuple[str, ...] = (
    "owasp_id",
    "severity",
    "score",
    "matched_patterns",
    "input_fingerprint",
    "detector",
)


def emit_injection_event(finding: InjectionFinding, text: str) -> None:
    """Emit the warning event for a triggered finding."""
    if not finding.triggered:
        return
    log.warning(
        "security.prompt_injection_detected",
        owasp_id=finding.owasp_id,
        severity=finding.severity.value,
        score=finding.score,
        matched_patterns=list(finding.matched_patterns),
        input_fingerprint=text_fingerprint(text),
        detector="pattern-v1",
    )
