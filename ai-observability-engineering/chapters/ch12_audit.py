"""Chapter 12: Audit Logging and Defensible Records."""

from __future__ import annotations

import hashlib
import json

from aiobs import Aiobs, Layer, MockProvider, Pillar, get_tracer
from aiobs.instrument import set_llm_attributes

from .registry import example

CONTEXT = "Refund extensions apply only to active products purchased after March 2025"


def _hash_chain(entries: list[dict]) -> list[str]:
    """Each entry's digest covers the previous digest.

    Not a blockchain. Just the minimum property an auditor asks for:
    you cannot quietly edit entry 3 without invalidating 4 through N.
    """
    digests: list[str] = []
    previous = "genesis"
    for entry in entries:
        payload = json.dumps(entry, sort_keys=True) + previous
        previous = hashlib.sha256(payload.encode()).hexdigest()
        digests.append(previous)
    return digests


@example(
    chapter=12,
    key="tamper_evident_audit_log",
    title="An audit record you can defend",
    pillar=Pillar.RISK,
    layer=Layer.BUSINESS_AND_OUTCOMES,
    listing="12.3",
)
def tamper_evident_audit_log() -> dict:
    """Records the decision, the inputs by reference, and who could see it.

    Note what is absent: the prompt text and the customer's data. The
    audit log points at them; it does not contain them.
    """
    tracer = get_tracer(__name__)
    provider = MockProvider()
    entries: list[dict] = []

    with tracer.start_as_current_span("audit_window") as root:
        root.set_attribute(Aiobs.PILLAR, Pillar.RISK.value)
        root.set_attribute(Aiobs.LAYER, Layer.BUSINESS_AND_OUTCOMES.value)
        for i in range(5):
            reply = provider.chat(f"claim {i}", context=CONTEXT)
            with tracer.start_as_current_span("chat") as span:
                set_llm_attributes(
                    span,
                    provider=provider.name,
                    model=reply.model,
                    input_tokens=reply.input_tokens,
                    output_tokens=reply.output_tokens,
                )
                entries.append(
                    {
                        "decision": "approve" if i % 2 else "refer",
                        "model": reply.model,
                        "trace_id": format(span.get_span_context().trace_id, "032x"),
                        "input_ref": f"vault://claims/{i}",
                        "policy_version": "refund-policy-2026-03",
                    }
                )
        digests = _hash_chain(entries)
        root.set_attribute("aiobs.audit.head_digest", digests[-1])
        root.set_attribute("aiobs.audit.entries", len(entries))

    tampered = list(entries)
    tampered[2] = {**tampered[2], "decision": "approve"}
    tampered_digests = _hash_chain(tampered)
    detected = tampered_digests[-1] != digests[-1]

    return {
        "entries": len(entries),
        "head_digest": digests[-1][:16],
        "tamper_detected": detected,
        "payload_stored_in_log": False,
    }
