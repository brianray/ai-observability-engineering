"""Hash-chained audit records (Listing 12.1).

Three properties an auditor asks for, in order of how often they are
missed:

1. **The record is complete.** It names the decision, the model, the
   policy version, and the inputs *by reference*. The prompt and the
   customer's data are not in it.
2. **The record is ordered.** Each record's digest covers the previous
   digest, so you cannot edit record 3 and leave 4 through N intact.
3. **The record cannot be quietly replaced.** That is the store's job,
   not the chain's, which is why ``AuditLogger`` requires one.

Note what is deliberately absent: there is no ``verify_chain`` method
here. Verifying the chain is Exercise 12.1, and the reference
implementation lives in ``verify_chain.py`` so a reader can check their
own answer without it being handed to them in the chapter text.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .append_only_store import AppendOnlyStore

GENESIS = "genesis"


def canonical_json(payload: dict[str, Any]) -> str:
    """Serialization that does not depend on dict ordering.

    Two records with the same content must hash identically no matter
    what order their keys were built in, or the chain breaks whenever
    someone refactors a dict literal.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def hash_record(payload: dict[str, Any], prev_hash: str) -> str:
    return hashlib.sha256((canonical_json(payload) + prev_hash).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AuditRecord:
    sequence: int
    timestamp: str
    payload: dict[str, Any]
    prev_hash: str
    record_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "timestamp": self.timestamp,
            "payload": self.payload,
            "prev_hash": self.prev_hash,
            "record_hash": self.record_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuditRecord:
        return cls(
            sequence=data["sequence"],
            timestamp=data["timestamp"],
            payload=data["payload"],
            prev_hash=data["prev_hash"],
            record_hash=data["record_hash"],
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AuditLogger:
    """Appends hash-chained records to an append-only store."""

    def __init__(self, store: AppendOnlyStore, *, clock=_now) -> None:
        self._store = store
        self._clock = clock
        self._head = GENESIS
        self._sequence = 0
        self._resume()

    def _resume(self) -> None:
        """Pick up the chain where a previous process left it."""
        keys = self._store.list_keys()
        if not keys:
            return
        last = AuditRecord.from_dict(json.loads(self._store.get(keys[-1])))
        self._head = last.record_hash
        self._sequence = last.sequence + 1

    @property
    def head(self) -> str:
        return self._head

    def append(self, payload: dict[str, Any], **_ignored: Any) -> AuditRecord:
        """Append one record and return it.

        The timestamp comes from the logger's clock, never from the
        caller. A caller-supplied timestamp is a caller-controlled
        ordering, and an audit log whose order the audited party chooses
        is not evidence. Any ``timestamp`` passed in is ignored.
        """
        body = {k: v for k, v in payload.items() if k != "timestamp"}
        record_body = {"sequence": self._sequence, "timestamp": self._clock(), "payload": body}
        record_hash = hash_record(record_body, self._head)

        record = AuditRecord(
            sequence=record_body["sequence"],
            timestamp=record_body["timestamp"],
            payload=body,
            prev_hash=self._head,
            record_hash=record_hash,
        )
        self._store.put(self._key(record.sequence), canonical_json(record.to_dict()).encode())
        self._head = record_hash
        self._sequence += 1
        return record

    @staticmethod
    def _key(sequence: int) -> str:
        # Zero-padded so lexical order is chain order, which is what
        # every store's list operation gives you.
        return f"{sequence:012d}.json"

    def records(self) -> list[AuditRecord]:
        return [
            AuditRecord.from_dict(json.loads(self._store.get(key)))
            for key in self._store.list_keys()
        ]
