"""Chapter 13 companion files."""

from .fairness_metrics import (
    DEFAULT_MIN_N,
    GAUGE_LABELS,
    FairnessReport,
    GaugeRecorder,
    GroupOutcomes,
    publish_fairness,
)
from .rag_quality import (
    FIXTURES,
    RagQualityResult,
    RagSample,
    deterministic_mock_judge,
    evaluate_rag_quality,
)

__all__ = [
    "DEFAULT_MIN_N",
    "FIXTURES",
    "GAUGE_LABELS",
    "FairnessReport",
    "GaugeRecorder",
    "GroupOutcomes",
    "RagQualityResult",
    "RagSample",
    "deterministic_mock_judge",
    "evaluate_rag_quality",
    "publish_fairness",
]
