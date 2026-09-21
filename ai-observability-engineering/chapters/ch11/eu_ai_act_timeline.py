"""EU AI Act application dates, as amended by the Digital Omnibus on AI.

Dates in a printed book age badly, and this set aged twice: the original
Regulation (EU) 2024/1689 schedule, then the deferral. Encoding them here
rather than only in prose means the chapter's claims are something CI can
check against a single source, and a reader can diff against the enacted
text without re-reading the chapter.

Verified for the manuscript against the amending regulation:
Regulation (EU) 2026/1744 ("Digital Omnibus on AI"), published in the
Official Journal 24 July 2026, in force 27 July 2026.

What the deferral does NOT touch is the part readers most often get
wrong, so it is modeled explicitly below rather than left implied.

The regulatory co-author should still sign off against the enacted text
before print; final legislative text can differ from provisional
agreements in particulars.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

#: The amending regulation.
DIGITAL_OMNIBUS_CELEX = "Regulation (EU) 2026/1744"
DIGITAL_OMNIBUS_PUBLISHED = date(2026, 7, 24)
DIGITAL_OMNIBUS_IN_FORCE = date(2026, 7, 27)


@dataclass(frozen=True)
class Obligation:
    key: str
    description: str
    applies_from: date
    #: The date this obligation would have applied from before the
    #: Digital Omnibus. ``None`` where the deferral did not move it.
    original_date: date | None = None

    @property
    def deferred(self) -> bool:
        return self.original_date is not None and self.original_date != self.applies_from


OBLIGATIONS: tuple[Obligation, ...] = (
    Obligation(
        key="prohibited_practices",
        description="Article 5 prohibited-practices list",
        applies_from=date(2025, 2, 2),
    ),
    Obligation(
        key="gpai_provider_obligations",
        description="General-purpose AI model provider obligations",
        applies_from=date(2025, 8, 2),
    ),
    Obligation(
        key="transparency_article_50",
        description="Article 50 transparency and labeling duties",
        applies_from=date(2026, 8, 2),
    ),
    Obligation(
        key="high_risk_annex_iii",
        description="Standalone high-risk systems (Annex III)",
        applies_from=date(2027, 12, 2),
        original_date=date(2026, 8, 2),
    ),
    Obligation(
        key="high_risk_annex_i",
        description="High-risk AI embedded in regulated products (Annex I)",
        applies_from=date(2028, 8, 2),
        original_date=date(2027, 8, 2),
    ),
)

#: The three the deferral leaves alone. Readers routinely assume the
#: Omnibus pushed everything back; it did not, and a provider who stops
#: labeling generated output on that assumption is non-compliant today.
UNAFFECTED_BY_DEFERRAL: tuple[str, ...] = (
    "transparency_article_50",
    "gpai_provider_obligations",
    "prohibited_practices",
)


def by_key(key: str) -> Obligation:
    for obligation in OBLIGATIONS:
        if obligation.key == key:
            return obligation
    raise KeyError(key)


def deferred_obligations() -> tuple[Obligation, ...]:
    return tuple(o for o in OBLIGATIONS if o.deferred)


def in_force_on(when: date) -> tuple[Obligation, ...]:
    return tuple(o for o in OBLIGATIONS if o.applies_from <= when)
