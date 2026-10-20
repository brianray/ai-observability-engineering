"""Chapter 13 companion files."""

from .cascade_judge import (
    FAITHFULNESS_QUESTION,
    JUDGE_FEES_USD_PER_1000,
    CascadeOutcome,
    CascadeReport,
    ListingJudgeEvaluator,
    evaluate_with_cascade,
)
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
    "FAITHFULNESS_QUESTION",
    "FIXTURES",
    "GAUGE_LABELS",
    "JUDGE_FEES_USD_PER_1000",
    "CascadeOutcome",
    "CascadeReport",
    "FairnessReport",
    "GaugeRecorder",
    "GroupOutcomes",
    "ListingJudgeEvaluator",
    "RagQualityResult",
    "RagSample",
    "deterministic_mock_judge",
    "evaluate_rag_quality",
    "evaluate_with_cascade",
    "publish_fairness",
]
