"""Observable code-generation wrapper with a verification-failure circuit breaker.

Companion file: chapters/ch16/codegen_breaker.py; composes with chapters/ch16/observable_tool.py
https://github.com/brianray/ai-observability-engineering/blob/main/ai-observability-engineering/chapters/ch16/codegen_breaker.py

"""
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from prometheus_client import Counter

from aiobs.logging import get_logger
from chapters.ch16.observable_tool import CircuitOpen

tracer = trace.get_tracer("aiobs.ch16", "1.0.0")
log = get_logger("aiobs.agents.codegen")

CODEGEN_VERIFICATIONS = Counter(
    "agent_codegen_verification_total",
    "generated-artifact verification outcomes",
    ["oracle", "outcome"],
)  # oracle: compile, test, sast, plan, policy, proof
  # outcome: pass, fail, error, skipped


class VerificationOutcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"
    SKIPPED = "skipped"


@dataclass
class VerificationResult:
    """A size-bounded, redacted verdict; never the raw artifact or its diff."""
    oracle: str
    outcome: VerificationOutcome
    detail: str = ""


class VerifiedCodeGenTool:
    """Wraps a code- or infrastructure-generating tool call with a nested
    verification span, so a call that succeeds as a tool call and fails
    every oracle it meets is visible as the failure it is.
    """

    def __init__(self, name: str, generate: Callable[..., str],
                 verifiers: list[Callable[[str], VerificationResult]],
                 fail_streak_limit: int = 3):
        self.name = name
        self.generate = generate
        self.verifiers = verifiers
        self.fail_streak_limit = fail_streak_limit
        self.fail_streak = 0

    def run(self, **kwargs) -> str:
        with tracer.start_as_current_span(f"codegen.{self.name}") as span:
            span.set_attribute("gen_ai.tool.name", self.name)
            artifact = self.generate(**kwargs)
            all_passed = True

            for verify in self.verifiers:
                with tracer.start_as_current_span(f"verify.{self.name}") as vspan:
                    result = verify(artifact)
                    vspan.set_attribute("codegen.oracle", result.oracle)
                    vspan.set_attribute("codegen.outcome", result.outcome.value)
                    CODEGEN_VERIFICATIONS.labels(
                        oracle=result.oracle, outcome=result.outcome.value,
                    ).inc()
                    if result.outcome is not VerificationOutcome.PASS:
                        all_passed = False
                        vspan.set_status(Status(StatusCode.ERROR, result.detail[:256]))
                        log.warning(
                            "codegen_verification_failed", tool=self.name,
                            oracle=result.oracle, outcome=result.outcome.value,
                        )

            self.fail_streak = 0 if all_passed else self.fail_streak + 1
            span.set_attribute("codegen.verified", all_passed)
            span.set_attribute("codegen.fail_streak", self.fail_streak)
            if self.fail_streak >= self.fail_streak_limit:
                raise CircuitOpen(
                    f"{self.name}: {self.fail_streak} consecutive generations "
                    "failed verification; likely a loop, not a fix"
                )
            return artifact
