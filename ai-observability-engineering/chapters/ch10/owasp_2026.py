"""STAGED: the 2025 -> 2026 OWASP LLM Top 10 renumbering. Not yet active.

Table 10.1 and every numbered citation in Chapter 10 are built on the
**2025** edition, which is what ``aiobs.risk.OwaspLLM`` encodes and what
every example still emits. OWASP published a **2026** edition that
reorders eight of the ten entries.

This module stages that change without making it. Nothing here is wired
into the detectors, the span attributes, or the examples: importing it
changes no behavior. It exists so the security co-author has a concrete,
reviewable artifact instead of a prose description, and so the flip is a
one-line change once sign-off lands.

**Do not activate without the security SME sign-off** that the Chapter 10
"SME REVIEW" boxes (Sections 10.2, 10.3, 10.4, 10.11) route to. Pearson's
editorial note asks for a reviewer with CISSP/CISM-level credentials plus
hands-on LLM red-teaming experience, and renumbering a security taxonomy
in a printed book without that review is how a wrong LLM0x number outlives
the edition.

**Provenance caveat.** The mapping below was transcribed from the
manuscript review packet. The 2026 edition could not be fetched from the
build environment (``genai.owasp.org`` and ``owasp.org`` are both
unreachable through the egress proxy), so it has **not** been verified
against the primary source from here. Verify before activating.
"""

from __future__ import annotations

from enum import Enum

from aiobs.risk import OwaspLLM

#: The edition ``OwaspLLM`` currently encodes and the examples emit.
ACTIVE_EDITION: str = "2025"

#: The staged edition. Published 2026-08-04.
STAGED_EDITION: str = "2026"


class OwaspLLM2026(str, Enum):
    """The 2026 ordering. Staged, not active."""

    PROMPT_INJECTION = "LLM01"
    SENSITIVE_INFORMATION_DISCLOSURE = "LLM02"
    EXCESSIVE_AGENCY = "LLM03"
    SUPPLY_CHAIN = "LLM04"
    DATA_AND_MODEL_POISONING = "LLM05"
    UNBOUNDED_CONSUMPTION = "LLM06"
    MISINFORMATION = "LLM07"
    HIDDEN_CONTEXT_EXPOSURE = "LLM08"
    VECTOR_AND_EMBEDDING_WEAKNESS = "LLM09"
    IMPROPER_OUTPUT_HANDLING = "LLM10"


#: 2025 id -> 2026 id. Eight of ten move.
RENUMBERING: dict[str, str] = {
    OwaspLLM.PROMPT_INJECTION.value: OwaspLLM2026.PROMPT_INJECTION.value,
    OwaspLLM.SENSITIVE_INFORMATION_DISCLOSURE.value: (
        OwaspLLM2026.SENSITIVE_INFORMATION_DISCLOSURE.value
    ),
    OwaspLLM.SUPPLY_CHAIN.value: OwaspLLM2026.SUPPLY_CHAIN.value,
    OwaspLLM.DATA_AND_MODEL_POISONING.value: OwaspLLM2026.DATA_AND_MODEL_POISONING.value,
    OwaspLLM.IMPROPER_OUTPUT_HANDLING.value: OwaspLLM2026.IMPROPER_OUTPUT_HANDLING.value,
    OwaspLLM.EXCESSIVE_AGENCY.value: OwaspLLM2026.EXCESSIVE_AGENCY.value,
    OwaspLLM.SYSTEM_PROMPT_LEAKAGE.value: OwaspLLM2026.HIDDEN_CONTEXT_EXPOSURE.value,
    OwaspLLM.VECTOR_AND_EMBEDDING_WEAKNESS.value: (
        OwaspLLM2026.VECTOR_AND_EMBEDDING_WEAKNESS.value
    ),
    OwaspLLM.MISINFORMATION.value: OwaspLLM2026.MISINFORMATION.value,
    OwaspLLM.UNBOUNDED_CONSUMPTION.value: OwaspLLM2026.UNBOUNDED_CONSUMPTION.value,
}

#: Entries that are not just renumbered. ``LLM07`` is the one that needs
#: prose changes rather than a find-and-replace: "System Prompt Leakage"
#: becomes "Hidden Context Exposure" and widens to cover any non-user
#: facing context an attacker can read back, not only the system prompt.
RENAMED: dict[str, tuple[str, str]] = {
    OwaspLLM.SYSTEM_PROMPT_LEAKAGE.value: (
        "Hidden Context Exposure",
        "Broadened from the system prompt specifically to any non-user-facing "
        "context an attacker can read back. Chapter 10's detector "
        "(detect_system_prompt_leak) covers the narrower 2025 framing only.",
    ),
}

#: Where the chapter's own running example lands. Excessive Agency is
#: Chapter 10's worked category, so this is the number that appears most
#: often in the prose and moves the furthest.
RUNNING_EXAMPLE_MOVE: tuple[str, str] = (
    OwaspLLM.EXCESSIVE_AGENCY.value,
    OwaspLLM2026.EXCESSIVE_AGENCY.value,
)

#: One sentence the chapter should carry: the 2026 ranking is 75%
#: practitioner consensus and 25% weighted by roughly 6,600-7,700
#: real-world incidents. That is the first time evidence has shaped the
#: list, which is itself a maturity signal worth naming in a book about
#: measuring things.
METHODOLOGY_NOTE: str = (
    "The 2026 edition ranks 75% by practitioner consensus and 25% by weighting "
    "against roughly 6,600-7,700 real-world incidents, the first edition in which "
    "incident evidence shaped the ordering. Project leads: Steve Wilson and Rock Lambros."
)

#: The Agentic list is a SEPARATE document (ASI01-ASI10, released
#: December 2025), not something the 2026 LLM release introduced. What
#: the 2026 release does add is an explicit scope boundary against it,
#: which is the cross-reference Chapter 10 should carry to Chapters 15-17.
AGENTIC_SCOPE_BOUNDARY: str = (
    "The 2026 LLM Top 10 draws an explicit scope boundary: once a model gains "
    "tools, memory, and autonomous consequences, the risk moves to the OWASP Top 10 "
    "for Agentic Applications (ASI01-ASI10, a separate document released December "
    "2025). In this book that boundary is Chapters 15 through 17."
)


def to_2026(owasp_id_2025: str) -> str:
    """Translate a 2025 id. Raises on an unknown id rather than passing it through."""
    try:
        return RENUMBERING[owasp_id_2025]
    except KeyError as exc:
        raise ValueError(f"{owasp_id_2025!r} is not a 2025 OWASP LLM id") from exc


def moved_entries() -> dict[str, str]:
    """The eight ids whose number changes."""
    return {old: new for old, new in RENUMBERING.items() if old != new}
