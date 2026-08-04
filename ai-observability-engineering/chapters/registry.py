"""Registry of every runnable example in the book.

One decorator registers an example and records the metadata the simulator
and the test suite need:

    @example(
        chapter=4,
        key="rag_pipeline",
        title="Tracing a RAG pipeline end to end",
        pillar=Pillar.PERFORMANCE,
        layer=Layer.DATA_AND_RETRIEVAL,
        listing="4.3",
    )
    def rag_pipeline() -> dict:
        ...

The metadata is not bookkeeping for its own sake. ``coverage()`` uses it
to report which pillars and layers have no examples exercising them, so a
gap in the book shows up as a gap in the repository.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from aiobs.pillars import ALL_LAYERS, ALL_PILLARS, Layer, Pillar

ExampleFn = Callable[[], Any]

CHAPTER_TITLES: dict[int, str] = {
    1: "The Observability Imperative for AI Systems",
    2: "Anatomy of an Observable AI System",
    3: "Signals, Scopes, and the Telemetry Contract",
    4: "Instrumenting LLM and Agent Pipelines with OpenTelemetry",
    5: "Performance Metrics That Matter",
    6: "Drift Detection and Behavioral Stability",
    7: "Accounting for AI Cost",
    8: "Engineering Cost Down",
    9: "Communicating ROI",
    10: "Security Threats Specific to LLMs",
    11: "Regulatory Frameworks and Compliance Mapping",
    12: "Audit Logging and Defensible Records",
    13: "Fairness and Quality as Monitored Metrics",
    14: "Human Oversight Patterns",
    15: "Tracing Multi-Agent Systems",
    16: "Cost and Failure Control in Agentic Systems",
    17: "Accountability When Responsibility Is Delegated",
}

PART_FOR_CHAPTER: dict[int, str] = {
    **dict.fromkeys((1, 2, 3), "Part I: Foundations of AI Observability"),
    **dict.fromkeys((4, 5, 6), "Part II: Performance Engineering"),
    **dict.fromkeys((7, 8, 9), "Part III: ROI Measurement"),
    **dict.fromkeys((10, 11, 12), "Part IV: Risk and Compliance"),
    **dict.fromkeys((13, 14), "Part V: Responsible AI Ops"),
    **dict.fromkeys((15, 16, 17), "Part VI: Agentic Systems"),
}


@dataclass(frozen=True)
class ExampleSpec:
    chapter: int
    key: str
    title: str
    pillar: Pillar
    layer: Layer
    func: ExampleFn
    listing: str | None = None
    expect_error: bool = False
    #: Set when the example deliberately demonstrates a failure. The
    #: harness still requires the instrumentation to be correct; what it
    #: relaxes is the expectation that the system behaved well.
    demonstrates_failure: bool = False
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def id(self) -> str:
        return f"ch{self.chapter:02d}.{self.key}"

    @property
    def part(self) -> str:
        return PART_FOR_CHAPTER[self.chapter]

    def __call__(self) -> Any:
        return self.func()


_EXAMPLES: dict[str, ExampleSpec] = {}


class DuplicateExampleError(ValueError):
    pass


def example(
    *,
    chapter: int,
    key: str,
    title: str,
    pillar: Pillar,
    layer: Layer,
    listing: str | None = None,
    expect_error: bool = False,
    demonstrates_failure: bool = False,
    tags: Iterable[str] = (),
) -> Callable[[ExampleFn], ExampleFn]:
    if chapter not in CHAPTER_TITLES:
        raise ValueError(f"chapter {chapter} is not one of 1-17")

    def decorator(func: ExampleFn) -> ExampleFn:
        spec = ExampleSpec(
            chapter=chapter,
            key=key,
            title=title,
            pillar=pillar,
            layer=layer,
            func=func,
            listing=listing,
            expect_error=expect_error,
            demonstrates_failure=demonstrates_failure,
            tags=tuple(tags),
        )
        if spec.id in _EXAMPLES:
            raise DuplicateExampleError(f"example {spec.id} is already registered")
        _EXAMPLES[spec.id] = spec
        func.__aiobs_spec__ = spec  # type: ignore[attr-defined]
        return func

    return decorator


def discover() -> None:
    """Import every ``chapters.chNN_*`` module so decorators run."""
    import chapters

    for module in pkgutil.iter_modules(chapters.__path__):
        if module.name.startswith("ch") and module.name[2:4].isdigit():
            importlib.import_module(f"chapters.{module.name}")


def all_examples(auto_discover: bool = True) -> list[ExampleSpec]:
    if auto_discover and not _EXAMPLES:
        discover()
    return sorted(_EXAMPLES.values(), key=lambda s: (s.chapter, s.key))


def for_chapter(chapter: int) -> list[ExampleSpec]:
    return [s for s in all_examples() if s.chapter == chapter]


def get(example_id: str) -> ExampleSpec:
    all_examples()
    try:
        return _EXAMPLES[example_id]
    except KeyError as exc:
        raise KeyError(
            f"unknown example {example_id!r}; try one of {sorted(_EXAMPLES)[:5]}..."
        ) from exc


def chapters_with_examples() -> list[int]:
    return sorted({s.chapter for s in all_examples()})


def coverage() -> dict[str, Any]:
    """Which pillars, layers, and chapters have examples, and which do not."""
    specs = all_examples()
    by_pillar = {p.value: [s.id for s in specs if s.pillar is p] for p in ALL_PILLARS}
    by_layer = {layer.value: [s.id for s in specs if s.layer is layer] for layer in ALL_LAYERS}
    covered_chapters = set(chapters_with_examples())
    return {
        "total_examples": len(specs),
        "by_pillar": by_pillar,
        "by_layer": by_layer,
        "uncovered_pillars": [k for k, v in by_pillar.items() if not v],
        "uncovered_layers": [k for k, v in by_layer.items() if not v],
        "uncovered_chapters": [c for c in CHAPTER_TITLES if c not in covered_chapters],
    }
