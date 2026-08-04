# Adding an example

Every listing in the book is a registered example here. Adding one to the manuscript means adding it here; nothing else has to change.

---

## The contract

An example is a zero-argument function that:

1. Emits at least one span
2. Uses only declared attribute namespaces (`gen_ai.*`, other OTel prefixes, `eval.*`, `aiobs.*`)
3. Puts no payload or PII into span attributes
4. Is deterministic: two runs produce identical span counts and token totals
5. Returns a JSON-serializable summary of what it demonstrated
6. Needs no API key, no network, and no local service

Point 4 is the one people miss. An example whose output moves between runs cannot be quoted in a book, because the number printed in the manuscript would be wrong by the time a reader ran it. Seed every random source. `MockProvider` is already seeded; `random.Random(fixed_seed)` for anything else.

Point 5 matters because the return value is what the chapter's behavior test asserts on, and what the HTML report displays.

---

## The shape

```python
"""Chapter 8: Engineering Cost Down."""

from __future__ import annotations

from aiobs import Aiobs, Layer, MockProvider, Pillar, get_tracer
from aiobs.instrument import set_cost_attributes, set_llm_attributes

from .registry import example


@example(
    chapter=8,
    key="prompt_compression",
    title="Cutting input tokens without moving quality",
    pillar=Pillar.ROI,
    layer=Layer.MODEL_AND_INFERENCE,
    listing="8.7",
)
def prompt_compression() -> dict:
    """One paragraph on what this demonstrates and why it is not obvious.

    Docstrings here are read by people deciding whether to run the
    example, so lead with the point, not the mechanism.
    """
    tracer = get_tracer(__name__)
    provider = MockProvider()

    with tracer.start_as_current_span("compression_experiment") as span:
        span.set_attribute(Aiobs.PILLAR, Pillar.ROI.value)
        span.set_attribute(Aiobs.LAYER, Layer.MODEL_AND_INFERENCE.value)
        ...

    return {"baseline_tokens": ..., "compressed_tokens": ..., "quality_delta": 0.0}
```

Then add a behavior test in `tests/functional/test_chapter_behavior.py`:

```python
def test_ch08_compression_cuts_tokens_without_moving_quality():
    payload = _run("ch08.prompt_compression").returned
    assert payload["compressed_tokens"] < payload["baseline_tokens"]
    assert abs(payload["quality_delta"]) < 0.05
```

`tests/functional/test_all_examples.py` picks the example up automatically. You do not have to register it anywhere else.

---

## Decorator arguments

| Argument | Required | Notes |
|---|---|---|
| `chapter` | yes | 1 to 17 |
| `key` | yes | snake_case, unique within the chapter |
| `title` | yes | one line, sentence case, appears in reports |
| `pillar` | yes | the pillar this example primarily serves |
| `layer` | yes | the layer it primarily instruments |
| `listing` | no | the listing number in the manuscript, e.g. `"8.7"` |
| `demonstrates_failure` | no | set when the point is to show something going wrong |
| `expect_error` | no | set when the example is supposed to raise |
| `tags` | no | free-form, e.g. `("exercise-1.1",)` |

`listing` is checked: the chapter part of the number must match the `chapter` argument, and no two examples may claim the same listing. That catches the copy-paste error where a new example inherits the number of the one above it.

`demonstrates_failure` does **not** relax the instrumentation contract. An example that shows a system behaving badly still has to be instrumented correctly; what it relaxes is your expectation that the returned numbers look good.

---

## Naming a new chapter module

`chapters/chNN_shortname.py`. The registry discovers any module matching `ch` + two digits. The short name is for humans and does not have to match anything.

---

## Attribute namespaces

Standardized attributes only from `aiobs.semconv.GenAI`. Never type the string:

```python
from aiobs.semconv import GenAI
span.set_attribute(GenAI.REQUEST_MODEL, model)     # yes
span.set_attribute("gen_ai.request.model", model)  # no
```

The indirection exists because the conventions are pre-1.0. When a name moves, one file changes.

New book-specific attributes go under `aiobs.` and are declared in `semconv.Aiobs`. New quality metrics go under `eval.` and are declared in `semconv.Eval`. Anything outside those namespaces fails `test_semconv_conformance.py`.

---

## Prose style in this repository

The docstrings are part of the book. Same voice.

- Say what the code demonstrates before saying what it does. A reader who already understands the mechanism will skip the mechanism.
- Comment the non-obvious decision, not the line. `# increment counter` is noise; `# Laplace smoothing keeps empty bins from producing infinities` is the reason someone will not delete the `+ 0.5` next year.
- Where a simplification exists for the book's sake, say so in the docstring. The heuristic evaluators carry an explicit "do not ship these as production quality gates" because someone will otherwise ship them.
- No em dashes.

---

## Before you open a pull request

```bash
make lint
make typecheck
make test
make sim
```

Or `make all`, which runs the four in order.

Check the coverage report if you are adding to a thin area:

```bash
aiobs-sim coverage
```

It reports declared coverage against coverage observed on actual spans. A pillar declared on an example but never tagged on a span means the example discusses the pillar without instrumenting it, which is worth fixing before it ships.
