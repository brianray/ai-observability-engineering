"""Append-only stores for the audit chain (ships alongside Listing 12.1).

The hash chain in ``audit_logger.py`` makes tampering *detectable*. It
does not make it *hard*. Anyone who can overwrite the file can recompute
every digest after the record they edited and hand you a chain that
verifies perfectly.

So the chain needs a store that refuses to overwrite. Two backends here:

``LocalFilesystemStore``
    ``O_CREAT | O_EXCL`` put-if-absent. Honest about what it is: enough
    for a laptop and for CI, not enough for an auditor, because root can
    still delete the file.

``S3ObjectLockStore``
    Object Lock in **compliance** mode with a configurable retention
    period. In compliance mode no principal, including the account root,
    can shorten the retention or delete the object before it expires.
    That is the property the auditor is actually asking about.

The S3 backend takes an injected client so the whole chapter runs in CI
without AWS. See README.md for the bucket configuration it requires.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol


class DuplicateKeyError(KeyError):
    """Raised when a key already exists. Append-only means append-only."""


class AppendOnlyStore(Protocol):
    """Put-if-absent, get, and ordered iteration. Deliberately no delete."""

    def put(self, key: str, payload: bytes) -> None: ...

    def get(self, key: str) -> bytes: ...

    def keys(self) -> list[str]: ...


@dataclass
class LocalFilesystemStore:
    """Put-if-absent via ``O_EXCL``. For development and CI."""

    root: Path

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        if "/" in key or "\\" in key or key in (".", ".."):
            raise ValueError(f"unsafe key {key!r}")
        return self.root / key

    def put(self, key: str, payload: bytes) -> None:
        # O_EXCL makes the create fail if the name already exists, and
        # the check-and-create is one syscall, so two writers racing for
        # the same key cannot both win.
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        try:
            fd = os.open(self._path(key), flags, 0o444)
        except FileExistsError as exc:
            raise DuplicateKeyError(f"{key!r} already exists; the store is append-only") from exc
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def keys(self) -> list[str]:
        return sorted(p.name for p in self.root.iterdir() if p.is_file())


class S3Client(Protocol):
    """The slice of the boto3 S3 client this store uses."""

    def put_object(self, **kwargs: Any) -> dict: ...

    def get_object(self, **kwargs: Any) -> dict: ...

    def head_object(self, **kwargs: Any) -> dict: ...

    def list_objects_v2(self, **kwargs: Any) -> dict: ...


@dataclass
class S3ObjectLockStore:
    """S3 with Object Lock in compliance mode.

    ``retention_days`` is the WORM window. Choose it from the retention
    obligation, not from storage cost: in compliance mode you cannot
    shorten it later, which is the point and also the foot-gun.
    """

    client: S3Client
    bucket: str
    prefix: str = "audit/"
    retention_days: int = 2555  # seven years, a common financial default
    #: GOVERNANCE lets a privileged principal override; COMPLIANCE does
    #: not. The chapter's claim only holds for COMPLIANCE.
    mode: str = "COMPLIANCE"

    def __post_init__(self) -> None:
        if self.mode != "COMPLIANCE":
            raise ValueError(
                "GOVERNANCE mode lets a sufficiently privileged principal delete the "
                "record, which is exactly the claim the audit chain is making. Use "
                "COMPLIANCE."
            )
        if self.retention_days <= 0:
            raise ValueError("retention_days must be positive")

    def _key(self, key: str) -> str:
        return f"{self.prefix}{key}"

    def _exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=self._key(key))
        except Exception:
            return False
        return True

    def put(self, key: str, payload: bytes) -> None:
        # S3 has no native put-if-absent for this API shape, so the guard
        # is a head first. It is a narrow race, and Object Lock closes
        # the consequence: an overwrite cannot destroy the locked version.
        if self._exists(key):
            raise DuplicateKeyError(f"{key!r} already exists; the store is append-only")

        retain_until = datetime.now(timezone.utc) + timedelta(days=self.retention_days)
        self.client.put_object(
            Bucket=self.bucket,
            Key=self._key(key),
            Body=payload,
            ObjectLockMode=self.mode,
            ObjectLockRetainUntilDate=retain_until,
        )

    def get(self, key: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=self._key(key))
        return response["Body"].read()

    def keys(self) -> list[str]:
        response = self.client.list_objects_v2(Bucket=self.bucket, Prefix=self.prefix)
        return sorted(
            item["Key"].removeprefix(self.prefix) for item in response.get("Contents", [])
        )
