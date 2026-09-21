"""Run the structural red-team fixtures and report pass rate by category.

One number ("93% of adversarial cases blocked") is the number that lets a
regression hide. If the suite is 80% instruction-override cases and the
detector quietly stops catching system-prompt extraction, the aggregate
barely moves. Reporting by category is what makes the regression visible.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import yaml

from .guardrails import BLOCK_THRESHOLD, input_guardrail

CASES_PATH = Path(__file__).with_name("adversarial_cases.yaml")


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    category: str
    expected: str
    observed: str

    @property
    def passed(self) -> bool:
        # Exact match on all three outcomes. An "allow" case tolerates
        # neither a block nor a flag: a flagged benign message still
        # costs a reviewer's time, so "close enough" is a failure here.
        return self.observed == self.expected


def load_cases(path: Path = CASES_PATH) -> list[dict]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    return list(doc["cases"])


def run_suite(path: Path = CASES_PATH, *, threshold: float = BLOCK_THRESHOLD) -> dict:
    """Evaluate every fixture and summarize by category."""
    results = [
        CaseResult(
            case_id=case["id"],
            category=case["category"],
            expected=case["expect"],
            observed=input_guardrail(case["text"], threshold=threshold).action,
        )
        for case in load_cases(path)
    ]

    by_category: dict[str, list[CaseResult]] = defaultdict(list)
    for result in results:
        by_category[result.category].append(result)

    categories = {
        category: {
            "total": len(items),
            "passed": sum(1 for i in items if i.passed),
            "pass_rate": round(sum(1 for i in items if i.passed) / len(items), 4),
        }
        for category, items in sorted(by_category.items())
    }

    passed = sum(1 for r in results if r.passed)
    return {
        "total": len(results),
        "passed": passed,
        "pass_rate": round(passed / len(results), 4) if results else 0.0,
        "by_category": categories,
        "failures": [r.case_id for r in results if not r.passed],
    }


if __name__ == "__main__":  # pragma: no cover - operator entry point
    import json

    print(json.dumps(run_suite(), indent=2))
