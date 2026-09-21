"""Chapter 17 companion files.

All three of Listings 17.1, 17.2 and 17.3 live under this package and are
re-exported from ``chapters/ch17_accountability.py``, which is the path
the manuscript cites.
"""

from .decision_record import DecisionRecord, assemble_decision_record
from .governance_checkpoint import (
    DECISION_APPROVE,
    DECISION_REJECT,
    DEFAULT_APPROVER_ROLES,
    ApprovalRequest,
    ApprovalResponse,
    make_governance_checkpoint,
)
from .responsibility_chain import (
    ChainNotStartedError,
    Hop,
    annotate_current_span,
    apply_context,
    carry_context,
    chain_as_json,
    current_chain,
    current_principal,
    delegate,
    release_context,
    start_chain,
)

__all__ = [
    "DECISION_APPROVE",
    "DECISION_REJECT",
    "DEFAULT_APPROVER_ROLES",
    "ApprovalRequest",
    "ApprovalResponse",
    "ChainNotStartedError",
    "DecisionRecord",
    "Hop",
    "annotate_current_span",
    "apply_context",
    "assemble_decision_record",
    "carry_context",
    "chain_as_json",
    "current_chain",
    "current_principal",
    "delegate",
    "make_governance_checkpoint",
    "release_context",
    "start_chain",
]
