"""Pinned attribute names for the book's instrumentation.

Chapter 1 argues that you should use the OpenTelemetry GenAI semantic
conventions rather than inventing attribute names, and that you should
isolate the convention strings behind a thin mapping layer because the
specification is still pre-1.0. This module is that mapping layer.

Every example in the book imports names from here. When the conventions
move, this file changes and nothing else does.

Two namespaces are in play:

``gen_ai.*``
    Standardized. Defined by the OpenTelemetry GenAI semantic conventions.
    Do not invent new attributes in this namespace.

``eval.*`` and ``aiobs.*``
    NOT standardized. The conventions do not yet define attributes for
    output quality, cost attribution, or governance. These are this book's
    own namespaces and are flagged as such wherever they appear.
"""

from __future__ import annotations

from typing import Final

#: The GenAI semantic convention version this repository is pinned to.
#: Verify against https://opentelemetry.io/docs/specs/semconv/gen-ai/
#: before relying on any specific attribute string in production.
SEMCONV_VERSION: Final[str] = "1.37.0"

#: The GenAI namespace. Everything model-related belongs here.
STANDARD_PREFIX: Final[str] = "gen_ai."

#: Other OpenTelemetry namespaces an AI service legitimately emits.
#: Listed explicitly rather than allowing anything with a dot, because
#: "it has a dot in it" is how an accidental attribute gets through.
OTEL_PREFIXES: Final[tuple[str, ...]] = (
    "gen_ai.",
    "http.",
    "db.",
    "rpc.",
    "messaging.",
    "server.",
    "client.",
    "network.",
    "url.",
    "user_agent.",
    "service.",
    "otel.",
    "code.",
    "exception.",
    "error.",
    "session.",
    "cloud.",
    "k8s.",
    "container.",
    "host.",
    "process.",
)

#: This book's own namespaces. Not standardized by anyone.
CUSTOM_PREFIXES: Final[tuple[str, ...]] = ("eval.", "aiobs.")


class GenAI:
    """Standardized ``gen_ai.*`` attributes (OTel GenAI semconv)."""

    PROVIDER_NAME: Final[str] = "gen_ai.provider.name"
    OPERATION_NAME: Final[str] = "gen_ai.operation.name"
    REQUEST_MODEL: Final[str] = "gen_ai.request.model"
    REQUEST_TEMPERATURE: Final[str] = "gen_ai.request.temperature"
    REQUEST_MAX_TOKENS: Final[str] = "gen_ai.request.max_tokens"
    RESPONSE_MODEL: Final[str] = "gen_ai.response.model"
    RESPONSE_ID: Final[str] = "gen_ai.response.id"
    RESPONSE_FINISH_REASONS: Final[str] = "gen_ai.response.finish_reasons"
    USAGE_INPUT_TOKENS: Final[str] = "gen_ai.usage.input_tokens"
    USAGE_OUTPUT_TOKENS: Final[str] = "gen_ai.usage.output_tokens"
    TOOL_NAME: Final[str] = "gen_ai.tool.name"
    AGENT_NAME: Final[str] = "gen_ai.agent.name"
    CONVERSATION_ID: Final[str] = "gen_ai.conversation.id"


class Operation:
    """Values for ``gen_ai.operation.name``."""

    CHAT: Final[str] = "chat"
    EMBEDDINGS: Final[str] = "embeddings"
    EXECUTE_TOOL: Final[str] = "execute_tool"
    INVOKE_AGENT: Final[str] = "invoke_agent"


class Eval:
    """CUSTOM. Output-quality attributes. Not defined by any specification."""

    HALLUCINATION_SCORE: Final[str] = "eval.hallucination_score"
    GROUNDEDNESS_SCORE: Final[str] = "eval.groundedness_score"
    RELEVANCE_SCORE: Final[str] = "eval.relevance_score"
    TOXICITY_SCORE: Final[str] = "eval.toxicity_score"
    EVALUATOR: Final[str] = "eval.evaluator"
    EVAL_SET_VERSION: Final[str] = "eval.set_version"


class Aiobs:
    """CUSTOM. Book-specific pillar, layer, cost, and governance attributes."""

    PILLAR: Final[str] = "aiobs.pillar"
    LAYER: Final[str] = "aiobs.layer"
    CHAPTER: Final[str] = "aiobs.chapter"
    EXAMPLE: Final[str] = "aiobs.example"

    COST_USD: Final[str] = "aiobs.cost.usd"
    COST_CURRENCY: Final[str] = "aiobs.cost.currency"
    COST_TENANT: Final[str] = "aiobs.cost.tenant"
    COST_USE_CASE: Final[str] = "aiobs.cost.use_case"
    REQUEST_ATTEMPTS: Final[str] = "aiobs.request.attempts"
    PURPOSE: Final[str] = "aiobs.purpose"

    RISK_INJECTION_DETECTED: Final[str] = "aiobs.risk.injection_detected"
    RISK_PII_DETECTED: Final[str] = "aiobs.risk.pii_detected"
    RISK_OWASP_ID: Final[str] = "aiobs.risk.owasp_id"

    #: Chapter 10. Set on every guarded call, including the allow path:
    #: a guardrail that only records its blocks cannot be audited for
    #: false negatives, because the denominator is missing.
    GUARDRAIL_INPUT_ACTION: Final[str] = "aiobs.guardrail.input.action"
    GUARDRAIL_OUTPUT_ACTION: Final[str] = "aiobs.guardrail.output.action"
    GUARDRAIL_SCORE: Final[str] = "aiobs.guardrail.score"

    #: Chapter 11. Compliance tagging.
    COMPLIANCE_SYSTEM_ID: Final[str] = "aiobs.compliance.system_id"
    COMPLIANCE_RISK_CATEGORY: Final[str] = "aiobs.compliance.risk_category"
    COMPLIANCE_FRAMEWORKS: Final[str] = "aiobs.compliance.frameworks"
    COMPLIANCE_CONTROLS: Final[str] = "aiobs.compliance.controls"
    COMPLIANCE_LAWFUL_BASIS: Final[str] = "aiobs.compliance.lawful_basis"
    COMPLIANCE_DPIA_REFERENCE: Final[str] = "aiobs.compliance.dpia_reference"
    RETENTION_CLASS: Final[str] = "aiobs.retention.class"

    #: Chapter 14. Human-in-the-loop routing.
    #:
    #: Listing 14.1 in the manuscript names these ``hitl.*``. A bare
    #: ``hitl.`` prefix is not a declared namespace in this repository
    #: (see CUSTOM_PREFIXES) and ``test_semconv_conformance.py`` rejects
    #: it, so the book's own rule applies: book-specific attributes live
    #: under ``aiobs.``. The manuscript listing needs the same prefix.
    HITL_ROUTED: Final[str] = "aiobs.hitl.routed"
    HITL_REASON: Final[str] = "aiobs.hitl.reason"
    HITL_QUEUE: Final[str] = "aiobs.hitl.queue"
    HITL_CONFIDENCE: Final[str] = "aiobs.hitl.confidence"

    #: Chapter 17. The delegation chain, serialized onto the current span.
    RESPONSIBILITY_CHAIN: Final[str] = "aiobs.responsibility.chain"
    RESPONSIBILITY_PRINCIPAL: Final[str] = "aiobs.responsibility.principal"

    DRIFT_SCORE: Final[str] = "aiobs.drift.score"
    DRIFT_METHOD: Final[str] = "aiobs.drift.method"

    HUMAN_REVIEW_REQUIRED: Final[str] = "aiobs.responsibility.review_required"
    HUMAN_REVIEW_OUTCOME: Final[str] = "aiobs.responsibility.review_outcome"

    MAST_FAILURE_MODE: Final[str] = "aiobs.agent.mast_failure_mode"
    AGENT_HANDOFF_DEPTH: Final[str] = "aiobs.agent.handoff_depth"


#: Attributes every LLM span must carry to be considered minimally
#: instrumented. Enforced by ``aiobs.testing.assertions.assert_llm_span``.
REQUIRED_LLM_ATTRIBUTES: Final[tuple[str, ...]] = (
    GenAI.PROVIDER_NAME,
    GenAI.OPERATION_NAME,
    GenAI.REQUEST_MODEL,
    GenAI.USAGE_INPUT_TOKENS,
    GenAI.USAGE_OUTPUT_TOKENS,
)


def is_genai(attribute: str) -> bool:
    """True if ``attribute`` is in the GenAI namespace specifically."""
    return attribute.startswith(STANDARD_PREFIX)


def is_standard(attribute: str) -> bool:
    """True if ``attribute`` belongs to any standardized OTel namespace."""
    return attribute.startswith(OTEL_PREFIXES)


def is_custom(attribute: str) -> bool:
    """True if ``attribute`` belongs to one of this book's namespaces."""
    return attribute.startswith(CUSTOM_PREFIXES)


def classify(attribute: str) -> str:
    """Return ``"standard"``, ``"custom"``, or ``"unknown"``.

    ``"unknown"`` is the interesting case. An attribute that is neither
    standardized nor deliberately namespaced is usually an accident, and
    the conformance test in ``tests/functional`` fails the build on it.
    """
    if is_standard(attribute):
        return "standard"
    if is_custom(attribute):
        return "custom"
    return "unknown"
