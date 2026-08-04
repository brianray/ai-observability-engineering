"""Risk detectors (Part IV, Chapters 10-12).

Pattern detectors mapped to the OWASP Top 10 for LLM Applications. These
are illustrative, not a security product: a regex that catches "ignore
previous instructions" catches the lazy attacker and nothing else. Their
job in this book is to give the Risk pillar something concrete to emit,
so a chapter can show what a risk signal looks like on a span.

Anything you deploy should be layered defense with a real classifier
behind it. Chapter 10 makes that argument at length.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum


class OwaspLLM(str, Enum):
    """OWASP Top 10 for LLM Applications identifiers used in this book."""

    PROMPT_INJECTION = "LLM01"
    SENSITIVE_INFORMATION_DISCLOSURE = "LLM02"
    SUPPLY_CHAIN = "LLM03"
    DATA_AND_MODEL_POISONING = "LLM04"
    IMPROPER_OUTPUT_HANDLING = "LLM05"
    EXCESSIVE_AGENCY = "LLM06"
    SYSTEM_PROMPT_LEAKAGE = "LLM07"
    VECTOR_AND_EMBEDDING_WEAKNESS = "LLM08"
    MISINFORMATION = "LLM09"
    UNBOUNDED_CONSUMPTION = "LLM10"


class Severity(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class Finding:
    owasp_id: str
    detector: str
    severity: Severity
    evidence: str

    def redacted(self) -> Finding:
        return Finding(self.owasp_id, self.detector, self.severity, "[redacted]")


@dataclass
class RiskReport:
    findings: list[Finding] = field(default_factory=list)

    @property
    def triggered(self) -> bool:
        return bool(self.findings)

    @property
    def max_severity(self) -> Severity:
        order = [Severity.NONE, Severity.LOW, Severity.MEDIUM, Severity.HIGH]
        if not self.findings:
            return Severity.NONE
        return max((f.severity for f in self.findings), key=order.index)

    def owasp_ids(self) -> list[str]:
        return sorted({f.owasp_id for f in self.findings})

    def redacted(self) -> RiskReport:
        """Findings with evidence stripped, safe to attach to a span.

        Chapter 12's rule: telemetry is not the place for the payload.
        Record that something fired and where to find the full record,
        never the attacker's string or the user's PII.
        """
        return RiskReport([f.redacted() for f in self.findings])


_INJECTION_PATTERNS: tuple[tuple[str, Severity], ...] = (
    (r"ignore (all )?(previous|prior|above) instructions", Severity.HIGH),
    (r"disregard (your|the) (system )?prompt", Severity.HIGH),
    (r"you are now (in )?(developer|god|admin|dan) mode", Severity.HIGH),
    (r"reveal (your|the) (system )?(prompt|instructions)", Severity.HIGH),
    (r"repeat (everything|the text) above", Severity.MEDIUM),
    (r"pretend (you are|to be) (an?ma|unrestricted|uncensored)", Severity.MEDIUM),
)

_PII_PATTERNS: tuple[tuple[str, str, Severity], ...] = (
    ("email", r"[\w.+-]+@[\w-]+\.[\w.]{2,}", Severity.MEDIUM),
    ("us_ssn", r"\b\d{3}-\d{2}-\d{4}\b", Severity.HIGH),
    ("credit_card", r"\b(?:\d[ -]*?){13,16}\b", Severity.HIGH),
    ("phone_e164", r"\+\d{10,15}\b", Severity.LOW),
)


def detect_prompt_injection(text: str) -> RiskReport:
    findings = [
        Finding(OwaspLLM.PROMPT_INJECTION.value, "pattern", severity, match.group(0))
        for pattern, severity in _INJECTION_PATTERNS
        for match in re.finditer(pattern, text, re.IGNORECASE)
    ]
    return RiskReport(findings)


def detect_pii(text: str) -> RiskReport:
    findings = [
        Finding(
            OwaspLLM.SENSITIVE_INFORMATION_DISCLOSURE.value, name, severity, match.group(0)
        )
        for name, pattern, severity in _PII_PATTERNS
        for match in re.finditer(pattern, text)
    ]
    return RiskReport(findings)


def detect_system_prompt_leak(output: str, system_prompt: str, shingle: int = 8) -> RiskReport:
    """Flag verbatim reproduction of the system prompt in the output.

    Word-shingle comparison rather than substring search, so a paraphrase
    that reorders a clause still trips the detector.
    """
    system_words = system_prompt.lower().split()
    if len(system_words) < shingle:
        return RiskReport()
    shingles = {
        " ".join(system_words[i : i + shingle])
        for i in range(len(system_words) - shingle + 1)
    }
    lowered = output.lower()
    hits = [s for s in shingles if s in lowered]
    if not hits:
        return RiskReport()
    return RiskReport(
        [
            Finding(
                OwaspLLM.SYSTEM_PROMPT_LEAKAGE.value,
                "shingle_match",
                Severity.HIGH,
                hits[0],
            )
        ]
    )


def scan(
    text: str,
    *,
    detectors: Iterable[str] = ("injection", "pii"),
) -> RiskReport:
    """Run the named detectors and merge their findings."""
    available = {"injection": detect_prompt_injection, "pii": detect_pii}
    merged: list[Finding] = []
    for name in detectors:
        try:
            detector = available[name]
        except KeyError as exc:
            raise ValueError(f"unknown detector: {name!r}") from exc
        merged.extend(detector(text).findings)
    return RiskReport(merged)
