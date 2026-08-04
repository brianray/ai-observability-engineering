"""Runs the book's examples and collects the results.

The simulator is not a demo. It is the thing that keeps the book honest:
every listing that appears in the manuscript is a registered example here,
and every registered example runs on every commit. If a listing in the
book stops working, this fails.
"""

from __future__ import annotations

import time
import traceback
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from aiobs.pillars import ALL_LAYERS, ALL_PILLARS
from aiobs.testing import ExampleHarness, HarnessResult
from chapters.registry import CHAPTER_TITLES, ExampleSpec, all_examples, for_chapter


@dataclass
class ExampleOutcome:
    spec: ExampleSpec
    result: HarnessResult
    duration_ms: float
    traceback_text: str = ""

    @property
    def status(self) -> str:
        if self.result.error is not None:
            return "ERROR"
        if self.result.violations:
            return "VIOLATION"
        return "PASS"

    @property
    def passed(self) -> bool:
        return self.status == "PASS"


@dataclass
class SimulationReport:
    outcomes: list[ExampleOutcome] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    duration_ms: float = 0.0

    # -- aggregates ----------------------------------------------------
    @property
    def total(self) -> int:
        return len(self.outcomes)

    @property
    def passed(self) -> int:
        return sum(1 for o in self.outcomes if o.passed)

    @property
    def failed(self) -> int:
        return self.total - self.passed

    @property
    def total_spans(self) -> int:
        return sum(len(o.result.spans) for o in self.outcomes)

    @property
    def total_llm_spans(self) -> int:
        return sum(o.result.llm_span_count for o in self.outcomes)

    @property
    def total_tokens(self) -> int:
        return sum(o.result.total_tokens for o in self.outcomes)

    @property
    def total_cost_usd(self) -> float:
        return round(sum(o.result.total_cost_usd for o in self.outcomes), 6)

    @property
    def ok(self) -> bool:
        return self.failed == 0

    # -- coverage ------------------------------------------------------
    def pillar_coverage(self) -> dict[str, dict[str, int]]:
        """Declared coverage vs coverage actually observed in the spans.

        The gap between the two columns is the interesting part. A pillar
        can be declared on an example and never appear on a span, which
        means the example talks about the pillar without instrumenting it.
        """
        declared = {p.value: 0 for p in ALL_PILLARS}
        observed = {p.value: 0 for p in ALL_PILLARS}
        for outcome in self.outcomes:
            declared[outcome.spec.pillar.value] += 1
            for pillar in outcome.result.pillars_covered():
                if pillar in observed:
                    observed[pillar] += 1
        return {k: {"declared": declared[k], "observed": observed[k]} for k in declared}

    def layer_coverage(self) -> dict[str, dict[str, int]]:
        declared = {layer.value: 0 for layer in ALL_LAYERS}
        observed = {layer.value: 0 for layer in ALL_LAYERS}
        for outcome in self.outcomes:
            declared[outcome.spec.layer.value] += 1
            for layer in outcome.result.layers_covered():
                if layer in observed:
                    observed[layer] += 1
        return {k: {"declared": declared[k], "observed": observed[k]} for k in declared}

    def by_chapter(self) -> dict[int, list[ExampleOutcome]]:
        grouped: dict[int, list[ExampleOutcome]] = {}
        for outcome in self.outcomes:
            grouped.setdefault(outcome.spec.chapter, []).append(outcome)
        return dict(sorted(grouped.items()))

    def failures(self) -> list[ExampleOutcome]:
        return [o for o in self.outcomes if not o.passed]

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "duration_ms": round(self.duration_ms, 3),
            "spans": self.total_spans,
            "llm_spans": self.total_llm_spans,
            "tokens": self.total_tokens,
            "cost_usd": self.total_cost_usd,
            "pillar_coverage": self.pillar_coverage(),
            "layer_coverage": self.layer_coverage(),
            "examples": [
                {
                    "id": o.spec.id,
                    "chapter": o.spec.chapter,
                    "chapter_title": CHAPTER_TITLES[o.spec.chapter],
                    "title": o.spec.title,
                    "listing": o.spec.listing,
                    "pillar": o.spec.pillar.value,
                    "layer": o.spec.layer.value,
                    "status": o.status,
                    "spans": len(o.result.spans),
                    "tokens": o.result.total_tokens,
                    "cost_usd": o.result.total_cost_usd,
                    "duration_ms": round(o.duration_ms, 3),
                    "violations": o.result.violations,
                    "error": str(o.result.error) if o.result.error else None,
                    "returned": _jsonable(o.result.returned),
                }
                for o in self.outcomes
            ],
        }


def _jsonable(value: object) -> object:
    """Best-effort conversion so a report can be serialized."""
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    return repr(value)


def select(
    chapter: int | None = None,
    example_ids: Sequence[str] | None = None,
    pillar: str | None = None,
) -> list[ExampleSpec]:
    specs = for_chapter(chapter) if chapter is not None else all_examples()
    if example_ids:
        wanted = set(example_ids)
        specs = [s for s in specs if s.id in wanted or s.key in wanted]
    if pillar:
        specs = [s for s in specs if s.pillar.value == pillar]
    return specs


def run(
    specs: Iterable[ExampleSpec] | None = None,
    *,
    strict: bool = True,
    on_result=None,
) -> SimulationReport:
    """Execute the selected examples through the harness.

    ``strict=False`` relaxes semantic-convention enforcement, which is
    useful when you are mid-refactor and want the examples to run before
    the attribute names are settled.
    """
    specs = list(specs if specs is not None else all_examples())
    harness = ExampleHarness(
        service_name="aiobs-simulator",
        require_semconv=strict,
        require_no_pii=strict,
    )
    report = SimulationReport()
    overall_started = time.perf_counter()

    for spec in specs:
        started = time.perf_counter()
        traceback_text = ""
        try:
            result = harness.run(spec.func, name=spec.id, expect_error=spec.expect_error)
        except BaseException as exc:
            result = HarnessResult(name=spec.id, error=exc)
            traceback_text = traceback.format_exc()
        else:
            if result.error is not None:
                traceback_text = "".join(
                    traceback.format_exception(
                        type(result.error), result.error, result.error.__traceback__
                    )
                )
        outcome = ExampleOutcome(
            spec=spec,
            result=result,
            duration_ms=(time.perf_counter() - started) * 1000,
            traceback_text=traceback_text,
        )
        report.outcomes.append(outcome)
        if on_result is not None:
            on_result(outcome)

    report.duration_ms = (time.perf_counter() - overall_started) * 1000
    return report
