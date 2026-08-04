"""The four pillars (Chapter 1) and the five observable layers (Chapter 2).

These are not decoration. Every example in the book declares which pillar
it serves and which layer it instruments, and the simulator uses those
declarations to report coverage: if a pillar or layer has no examples
exercising it, that shows up as a gap rather than passing silently.
"""

from __future__ import annotations

from enum import Enum


class Pillar(str, Enum):
    """Chapter 1: the four questions no single one of the others answers."""

    PERFORMANCE = "performance"
    ROI = "roi"
    RISK = "risk"
    RESPONSIBILITY = "responsibility"

    @property
    def question(self) -> str:
        return _PILLAR_QUESTIONS[self]

    @property
    def parts(self) -> tuple[str, ...]:
        return _PILLAR_PARTS[self]


_PILLAR_QUESTIONS: dict[Pillar, str] = {
    Pillar.PERFORMANCE: "Is it fast, reliable, and stable enough to trust in production?",
    Pillar.ROI: "Is it worth what it costs?",
    Pillar.RISK: "Can it be exploited, and what does operating it expose us to?",
    Pillar.RESPONSIBILITY: "Is it fair, and who is accountable when it isn't?",
}

_PILLAR_PARTS: dict[Pillar, tuple[str, ...]] = {
    Pillar.PERFORMANCE: ("Part II (Chapters 4-6)",),
    Pillar.ROI: ("Part III (Chapters 7-9)",),
    Pillar.RISK: ("Part IV (Chapters 10-12)",),
    Pillar.RESPONSIBILITY: ("Part V (Chapters 13-14)", "Part VI (Chapters 15-17)"),
}


class Layer(str, Enum):
    """Chapter 2: the five observable layers of a production AI system."""

    INFRASTRUCTURE = "infrastructure"
    MODEL_AND_INFERENCE = "model_and_inference"
    DATA_AND_RETRIEVAL = "data_and_retrieval"
    APPLICATION_AND_ORCHESTRATION = "application_and_orchestration"
    BUSINESS_AND_OUTCOMES = "business_and_outcomes"

    @property
    def otel_coverage(self) -> str:
        """How well OpenTelemetry covers this layer out of the box.

        Chapter 2's recurring structural argument: OTel is strong in the
        middle three layers and thin at both edges.
        """
        return _LAYER_COVERAGE[self]


_LAYER_COVERAGE: dict[Layer, str] = {
    Layer.INFRASTRUCTURE: "partial",
    Layer.MODEL_AND_INFERENCE: "strong",
    Layer.DATA_AND_RETRIEVAL: "strong",
    Layer.APPLICATION_AND_ORCHESTRATION: "strong",
    Layer.BUSINESS_AND_OUTCOMES: "thin",
}


class Scope(str, Enum):
    """The four-level scope hierarchy used throughout the book."""

    SPAN = "span"
    TRACE = "trace"
    SESSION = "session"
    EXPERIMENT = "experiment"


ALL_PILLARS: tuple[Pillar, ...] = tuple(Pillar)
ALL_LAYERS: tuple[Layer, ...] = tuple(Layer)
