"""Who could see what, and for how long (Listing 12.2).

The audit record says a decision was made. The custody record says which
data the decision touched, which store it lives in, who had read access
at the time, and when it must be destroyed. An auditor asks for both, and
the second one is the one nobody has.

Custody entries reference payloads; they never contain them. Chapter 12's
rule holds here as everywhere: the log points at the data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum


class DataClass(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"   # special-category / regulated personal data


#: Retention in days by classification. A retention period that is not
#: written down is a retention period of "forever", which is its own
#: finding under most regimes.
RETENTION_DAYS: dict[DataClass, int] = {
    DataClass.PUBLIC: 365,
    DataClass.INTERNAL: 730,
    DataClass.CONFIDENTIAL: 1825,
    DataClass.RESTRICTED: 2555,
}


@dataclass(frozen=True)
class CustodyEntry:
    """One piece of data a decision touched."""

    reference: str              # vault:// URI. Never the payload.
    data_class: DataClass
    store: str
    readers: tuple[str, ...]    # roles, not individuals
    acquired_on: date
    purpose: str

    @property
    def destroy_after(self) -> date:
        return self.acquired_on + timedelta(days=RETENTION_DAYS[self.data_class])

    def is_overdue(self, today: date) -> bool:
        return today > self.destroy_after

    def to_dict(self) -> dict:
        return {
            "reference": self.reference,
            "data_class": self.data_class.value,
            "store": self.store,
            "readers": list(self.readers),
            "acquired_on": self.acquired_on.isoformat(),
            "destroy_after": self.destroy_after.isoformat(),
            "purpose": self.purpose,
        }


class CustodyLedger:
    """The custody side of the dossier."""

    def __init__(self) -> None:
        self._entries: dict[str, list[CustodyEntry]] = {}

    def record(self, decision_id: str, entry: CustodyEntry) -> None:
        if "://" not in entry.reference:
            raise ValueError(
                f"{entry.reference!r} is not a reference. Custody entries point at "
                "data; they do not carry it."
            )
        self._entries.setdefault(decision_id, []).append(entry)

    def for_decision(self, decision_id: str) -> list[CustodyEntry]:
        return list(self._entries.get(decision_id, []))

    def overdue(self, today: date) -> list[tuple[str, CustodyEntry]]:
        return [
            (decision_id, entry)
            for decision_id, entries in self._entries.items()
            for entry in entries
            if entry.is_overdue(today)
        ]
