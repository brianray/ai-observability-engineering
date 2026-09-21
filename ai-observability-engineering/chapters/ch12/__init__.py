"""Chapter 12 companion files."""

from .append_only_store import (
    AppendOnlyStore,
    DuplicateKeyError,
    LocalFilesystemStore,
    S3ObjectLockStore,
)
from .audit_logger import AuditLogger, AuditRecord, canonical_json, hash_record
from .audit_queries import Dossier, assemble_dossier
from .data_custody import CustodyEntry, CustodyLedger, DataClass
from .verify_chain import VerificationResult, verify_chain

__all__ = [
    "AppendOnlyStore",
    "AuditLogger",
    "AuditRecord",
    "CustodyEntry",
    "CustodyLedger",
    "DataClass",
    "Dossier",
    "DuplicateKeyError",
    "LocalFilesystemStore",
    "S3ObjectLockStore",
    "VerificationResult",
    "assemble_dossier",
    "canonical_json",
    "hash_record",
    "verify_chain",
]
