"""Reference solution to Exercise 12.1. NOT reproduced in the chapter text.

The exercise asks the reader to write chain verification themselves. This
file exists so they can check their answer, which means the chapter body
must not contain it and ``audit_logger.AuditLogger`` must not expose it
as a method.

The property worth getting right is the cascade: altering record 3
invalidates 3 *and everything after it*, because each digest covers the
previous one. A verifier that reports only the edited record has missed
the point of chaining.
"""

from __future__ import annotations

from dataclasses import dataclass

from .audit_logger import GENESIS, AuditRecord, hash_record


@dataclass(frozen=True)
class VerificationResult:
    verified: bool
    #: Sequence numbers that could not be verified, in order. On a
    #: tampered chain this is the edited record and every later one.
    unverifiable: tuple[int, ...]
    reason: str = ""


def verify_chain(records: list[AuditRecord]) -> VerificationResult:
    """Recompute every digest and report the first break and its cascade."""
    if not records:
        return VerificationResult(True, ())

    expected_prev = GENESIS
    for index, record in enumerate(records):
        body = {
            "sequence": record.sequence,
            "timestamp": record.timestamp,
            "payload": record.payload,
        }
        recomputed = hash_record(body, expected_prev)

        if record.prev_hash != expected_prev:
            return VerificationResult(
                False,
                tuple(r.sequence for r in records[index:]),
                f"record {record.sequence} does not link to the previous record",
            )
        if recomputed != record.record_hash:
            # Everything after this point is unverifiable too: their
            # digests were computed over a hash we can no longer trust.
            return VerificationResult(
                False,
                tuple(r.sequence for r in records[index:]),
                f"record {record.sequence} payload does not match its digest",
            )
        expected_prev = record.record_hash

    return VerificationResult(True, ())
