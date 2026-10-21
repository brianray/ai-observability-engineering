"""Unit tests: Listing 16.4, the verified code-generation wrapper.

``prometheus_client`` is an optional extra (``pip install -e ".[metrics]"``),
so the module is skipped rather than failed when it is not installed.
"""

from __future__ import annotations

import pytest

pytest.importorskip("prometheus_client")

from chapters.ch16.codegen_breaker import (  # noqa: E402
    VerificationOutcome,
    VerificationResult,
    VerifiedCodeGenTool,
)
from chapters.ch16.observable_tool import CircuitOpen  # noqa: E402


def _passing(artifact: str) -> VerificationResult:
    return VerificationResult(oracle="compile", outcome=VerificationOutcome.PASS)


def _failing(artifact: str) -> VerificationResult:
    return VerificationResult(oracle="test", outcome=VerificationOutcome.FAIL, detail="2 tests failed")


def test_passing_generation_returns_the_artifact_and_resets_the_streak():
    tool = VerifiedCodeGenTool("terraform", lambda **kw: "resource {}", [_passing])
    tool.fail_streak = 2
    assert tool.run(prompt="make a bucket") == "resource {}"
    assert tool.fail_streak == 0


def test_a_failed_oracle_counts_toward_the_streak_but_still_returns():
    tool = VerifiedCodeGenTool("terraform", lambda **kw: "resource {}", [_passing, _failing])
    assert tool.run() == "resource {}"
    assert tool.fail_streak == 1


def test_breaker_opens_after_the_configured_streak():
    tool = VerifiedCodeGenTool("terraform", lambda **kw: "x", [_failing], fail_streak_limit=3)
    tool.run()
    tool.run()
    with pytest.raises(CircuitOpen):
        tool.run()
    assert tool.fail_streak == 3


def test_detail_is_bounded_on_the_span_status():
    long_detail = "x" * 1000
    def noisy(artifact: str) -> VerificationResult:
        return VerificationResult(oracle="sast", outcome=VerificationOutcome.ERROR, detail=long_detail)
    tool = VerifiedCodeGenTool("gen", lambda **kw: "y", [noisy], fail_streak_limit=5)
    tool.run()  # must not raise; the status description is sliced to 256 chars inside run()
    assert tool.fail_streak == 1
