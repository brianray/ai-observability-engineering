"""Unit tests: Chapter 12 audit companion."""

from __future__ import annotations

import io
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from chapters.ch12 import (
    AuditLogger,
    CustodyEntry,
    CustodyLedger,
    DataClass,
    DuplicateKeyError,
    LocalFilesystemStore,
    S3ObjectLockStore,
    assemble_dossier,
    canonical_json,
    verify_chain,
)


@pytest.fixture()
def logger(tmp_path):
    return AuditLogger(LocalFilesystemStore(tmp_path / "audit"))


def _payload(i: int, subject: str = "subject-7") -> dict:
    return {
        "decision_id": f"dec-{i}",
        "subject_ref": subject,
        "decision": "approve" if i % 2 else "refer",
        "model": "mock-sonnet-1",
        "policy_version": "refund-policy-2026-03",
        "trace_id": f"{i:032x}",
        "input_ref": f"vault://claims/{i}",
    }


# --- chain ---


def test_two_appends_link_prev_hash_to_record_hash(logger):
    first = logger.append(_payload(0))
    second = logger.append(_payload(1))

    assert first.prev_hash == "genesis"
    assert second.prev_hash == first.record_hash
    assert second.sequence == first.sequence + 1
    assert verify_chain([first, second]).verified


def test_canonical_serialization_is_stable_across_key_order():
    a = {"b": 2, "a": 1, "c": {"z": 1, "y": 2}}
    b = {"c": {"y": 2, "z": 1}, "a": 1, "b": 2}
    assert canonical_json(a) == canonical_json(b)


def test_tampering_invalidates_that_record_and_every_later_one(logger):
    for i in range(5):
        logger.append(_payload(i))

    records = logger.records()
    tampered = list(records)
    altered = tampered[2]
    tampered[2] = type(altered)(
        sequence=altered.sequence,
        timestamp=altered.timestamp,
        payload={**altered.payload, "decision": "approve"},
        prev_hash=altered.prev_hash,
        record_hash=altered.record_hash,
    )

    result = verify_chain(tampered)
    assert not result.verified
    # The cascade is the point of chaining: 2, 3 and 4 are all suspect.
    assert result.unverifiable == (2, 3, 4)


def test_an_untouched_chain_verifies(logger):
    for i in range(4):
        logger.append(_payload(i))
    assert verify_chain(logger.records()).verified


def test_verify_chain_is_not_a_method_on_the_logger():
    """Exercise 12.1 stays an exercise."""
    assert not hasattr(AuditLogger, "verify_chain")


def test_caller_supplied_timestamp_is_ignored(logger):
    record = logger.append({**_payload(0), "timestamp": "1999-01-01T00:00:00+00:00"})
    assert not record.timestamp.startswith("1999")
    assert "timestamp" not in record.payload


def test_logger_resumes_an_existing_chain(tmp_path):
    store = LocalFilesystemStore(tmp_path / "audit")
    first = AuditLogger(store).append(_payload(0))

    resumed = AuditLogger(store)
    second = resumed.append(_payload(1))
    assert second.prev_hash == first.record_hash
    assert verify_chain(resumed.records()).verified


# --- stores ---


def test_local_store_raises_on_a_duplicate_key(tmp_path):
    store = LocalFilesystemStore(tmp_path / "s")
    store.put("k.json", b"one")
    with pytest.raises(DuplicateKeyError):
        store.put("k.json", b"two")
    assert store.get("k.json") == b"one"


def test_local_store_rejects_a_path_traversing_key(tmp_path):
    store = LocalFilesystemStore(tmp_path / "s")
    with pytest.raises(ValueError):
        store.put("../escape.json", b"x")


class FakeS3:
    def __init__(self):
        self.objects: dict[str, dict] = {}

    def put_object(self, **kw):
        self.objects[kw["Key"]] = kw
        return {}

    def get_object(self, **kw):
        return {"Body": io.BytesIO(self.objects[kw["Key"]]["Body"])}

    def head_object(self, **kw):
        if kw["Key"] not in self.objects:
            raise KeyError(kw["Key"])
        return {}

    def list_objects_v2(self, **kw):
        prefix = kw.get("Prefix", "")
        return {"Contents": [{"Key": k} for k in self.objects if k.startswith(prefix)]}


def test_s3_store_writes_compliance_mode_with_a_retention_date():
    client = FakeS3()
    store = S3ObjectLockStore(client=client, bucket="b", retention_days=2555)
    store.put("000.json", b"record")

    written = client.objects["audit/000.json"]
    assert written["ObjectLockMode"] == "COMPLIANCE"
    expected = datetime.now(timezone.utc) + timedelta(days=2555)
    assert abs((written["ObjectLockRetainUntilDate"] - expected).total_seconds()) < 60


def test_s3_store_refuses_governance_mode():
    """GOVERNANCE lets a privileged principal delete the evidence."""
    with pytest.raises(ValueError, match="COMPLIANCE"):
        S3ObjectLockStore(client=FakeS3(), bucket="b", mode="GOVERNANCE")


def test_s3_store_raises_on_a_duplicate_key():
    store = S3ObjectLockStore(client=FakeS3(), bucket="b")
    store.put("k.json", b"one")
    with pytest.raises(DuplicateKeyError):
        store.put("k.json", b"two")


def test_audit_logger_runs_against_the_s3_backend():
    store = S3ObjectLockStore(client=FakeS3(), bucket="b")
    audit = AuditLogger(store)
    audit.append(_payload(0))
    audit.append(_payload(1))
    assert verify_chain(audit.records()).verified


# --- custody + dossier ---


def test_custody_entry_refuses_a_payload_in_place_of_a_reference():
    ledger = CustodyLedger()
    with pytest.raises(ValueError):
        ledger.record(
            "dec-0",
            CustodyEntry(
                reference="the customer said their card ending 4242 was declined",
                data_class=DataClass.RESTRICTED,
                store="vault",
                readers=("credit-ops",),
                acquired_on=date(2026, 1, 1),
                purpose="decision",
            ),
        )


def test_retention_is_derived_from_the_data_class():
    entry = CustodyEntry(
        reference="vault://claims/0",
        data_class=DataClass.RESTRICTED,
        store="vault",
        readers=("credit-ops",),
        acquired_on=date(2026, 1, 1),
        purpose="decision",
    )
    assert entry.destroy_after == date(2026, 1, 1) + timedelta(days=2555)
    assert entry.is_overdue(date(2040, 1, 1))
    assert not entry.is_overdue(date(2027, 1, 1))


def test_full_dossier_assembles_end_to_end(logger):
    custody = CustodyLedger()
    for i in range(4):
        logger.append(_payload(i))
        custody.record(
            f"dec-{i}",
            CustodyEntry(
                reference=f"vault://claims/{i}",
                data_class=DataClass.CONFIDENTIAL,
                store="claims-vault",
                readers=("credit-ops", "audit"),
                acquired_on=date(2026, 1, 1),
                purpose="refund eligibility decision",
            ),
        )
    logger.append(_payload(9, subject="someone-else"))

    today = date.today()
    dossier = assemble_dossier(
        logger,
        custody,
        subject_ref="subject-7",
        period_start=today - timedelta(days=1),
        period_end=today + timedelta(days=1),
    )

    assert len(dossier.decisions) == 4
    assert dossier.defensible
    assert all(d["custody"] for d in dossier.decisions)
    assert json.dumps(dossier.to_dict(), default=str)


def test_a_dossier_from_a_broken_chain_is_not_defensible(logger, tmp_path):
    for i in range(3):
        logger.append(_payload(i))

    store = LocalFilesystemStore(tmp_path / "audit")
    key = store.keys()[1]
    raw = json.loads(store.get(key))
    assert raw["payload"]["decision"] != "overturned"  # the edit must be a real change
    raw["payload"]["decision"] = "overturned"
    (tmp_path / "audit" / key).chmod(0o644)
    (tmp_path / "audit" / key).write_text(canonical_json(raw), encoding="utf-8")

    today = date.today()
    dossier = assemble_dossier(
        AuditLogger(store),
        CustodyLedger(),
        subject_ref="subject-7",
        period_start=today - timedelta(days=1),
        period_end=today + timedelta(days=1),
    )
    assert not dossier.defensible
