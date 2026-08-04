# Testing instrumentation

Instrumentation is code. Untested code rots, and rotted instrumentation is worse than none, because it produces a dashboard that is confidently wrong.

This document covers what the harness checks, why each check exists, and how to point it at instrumentation you already have.

---

## Two layers of test

**Unit tests** (`tests/unit/`, 96 tests) cover the framework internals: attribute namespaces, cost arithmetic, drift estimators, evaluator ranking, risk detectors, MAST classification, and the harness itself. They are fast and have no I/O.

**Functional tests** (`tests/functional/`, 251 tests) cover behavior end to end:

| File | Asserts |
|---|---|
| `test_all_examples.py` | every registered example runs, emits spans, and is deterministic across two runs |
| `test_semconv_conformance.py` | no example emits an attribute outside a declared namespace, ever |
| `test_chapter_behavior.py` | each chapter's examples demonstrate what the chapter claims |
| `test_simulator.py` | the simulator itself, including that a broken example is reported rather than raised |

`test_chapter_behavior.py` is the unusual one and the most valuable. The other files prove the code runs. This one proves the argument holds. If Chapter 5 says the mean hides the tail, there is a test asserting `p99 > 2 × mean` for that chapter's example. If Chapter 13 says an aggregate hides a cohort gap, there is a test asserting the aggregate sits between the two cohort means. When a chapter's own code stops demonstrating the chapter's point, that is the bug worth catching before a reader finds it.

```bash
pytest                      # everything
pytest tests/unit -x        # fast loop while developing
pytest -k ch06              # one chapter
pytest --cov                # coverage
```

---

## What the harness checks

`ExampleHarness` applies four contracts to every span:

### 1. Semantic convention compliance

Every attribute must be in a declared namespace: a standardized OpenTelemetry prefix, or one of this book's (`eval.`, `aiobs.`). Anything else fails.

This is the most likely test to fail on a pull request, and that is intended. An accidental attribute costs nothing to fix now and a great deal to fix after two teams have built dashboards on it. The specific case this guards is `llm.*`, which early drafts of the book used and which was never a convention at all.

### 2. The model-invoking span contract

A span whose `gen_ai.operation.name` is `chat`, `text_completion`, or `embeddings` must carry provider, model, and integer token counts. String token counts fail; so do negative ones.

Spans with operation `invoke_agent` or `execute_tool` are GenAI spans too, but they have no model of their own. They are checked with `assert_genai_span`, which requires operation and provider and nothing more. Demanding a model produces the fake `model="n/a"` attribute that makes traces harder to read rather than easier.

### 3. No PII in telemetry

No span attribute value may match an email address, US SSN, or card number pattern. Chapter 12's rule: telemetry records that something happened, not the payload it happened to. Record a reference instead:

```python
span.set_attribute("aiobs.risk.evidence_ref", "vault://prompts/1234")
```

Without this, a debugging session becomes a second incident.

### 4. Something was emitted

An example that produces no spans fails. Silence is the failure mode that looks like success.

---

## The assertion set

```python
from aiobs.testing import (
    assert_llm_span, assert_genai_span, assert_semconv_compliant, assert_no_pii,
    assert_same_trace, assert_parent_of, assert_cost_attributed, assert_evaluated,
    assert_span_count, assert_has_attributes, assert_attribute,
    assert_attribute_between, assert_ok, assert_error,
    spans_named, spans_with_attribute, llm_spans, genai_spans, root_spans,
)
```

Each raises `SpanAssertionError` with a message naming the span, the attribute, and what was found instead. An assertion that says only `AssertionError: False is not true` costs more time than it saves.

Two worth calling out:

**`assert_same_trace`** catches broken context propagation across an async boundary or a thread pool. That failure produces orphaned traces which look fine individually and are useless for debugging a request end to end. It is invisible without this check.

**`assert_cost_attributed`** fails when a span records cost with `tenant="unattributed"`. Note that `set_cost_attributes` always writes the tenant, defaulting to `"unattributed"` rather than omitting it. Omitting makes unattributed spend invisible; recording it makes it countable, which is what Chapter 9 needs in order to report it.

---

## Testing your own instrumentation

Nothing in the harness is specific to this book's examples. Point it at your code.

```python
# conftest.py
pytest_plugins = ["aiobs.testing.fixtures"]
```

```python
from aiobs.testing import ExampleHarness

def test_support_pipeline_is_instrumented():
    result = ExampleHarness().run(handle_support_ticket, "my ticket text")
    assert result.ok, result.violations
    assert result.llm_span_count == 2
    assert result.total_cost_usd < 0.05
    assert "responsibility" in result.pillars_covered()
```

Or with the capture context manager, if you want to assert on spans directly:

```python
from aiobs import capture
from aiobs.testing import assert_same_trace, llm_spans, spans_named

def test_retrieval_precedes_generation():
    with capture() as spans:
        handle_support_ticket("my ticket text")

    assert_same_trace(spans)
    retrieval = spans_named(spans, "vector_search")[0]
    generation = llm_spans(spans)[0]
    assert retrieval.end_time <= generation.start_time
```

### unittest

```python
from aiobs.testing import ObservabilityTestCase

class TestSupportPipeline(ObservabilityTestCase):
    service_name = "support-assistant"

    def test_instrumentation(self):
        with self.capture_spans():
            handle_support_ticket("my ticket text")
        self.assertLLMSpanCount(2)
        self.assertAllSpansCompliant()
        self.assertAllLLMSpansValid()
        self.assertSingleTrace()
        self.assertNoPII()
        self.assertPillarCovered("responsibility")
```

---

## Fixtures

From `aiobs.testing.fixtures`:

| Fixture | Provides |
|---|---|
| `_isolated_telemetry` | autouse; fresh tracer and empty span buffer per test |
| `spans` | callable returning spans finished so far |
| `provider` | seeded `MockProvider` |
| `failing_provider` | `MockProvider` in `CONFIDENTLY_WRONG` mode |
| `harness` | a configured `ExampleHarness` |
| `evals` | the default evaluator suite |
| `knowledge_base` | small fixed corpus for retrieval tests |

`_isolated_telemetry` is autouse on purpose. A span leaked from a previous test is the single most common source of a flaky instrumentation suite, and the symptom (a test that passes alone and fails in the suite) sends people looking in the wrong place for hours.

---

## Failure modes you can script

`MockProvider(failure_mode=...)` reproduces specific production failures deterministically:

| Mode | Behavior |
|---|---|
| `NONE` | grounded answer drawn from the supplied context |
| `CONFIDENTLY_WRONG` | fluent, absolute, factually false; status 200, latency normal |
| `UNGROUNDED` | answers from the model rather than the retrieved corpus |
| `RETRY_LOOP` | repeats a step without progress (MAST FM-1.3) |
| `NO_TERMINATION` | never declares the task finished (MAST FM-1.5) |
| `DRIFT` | output distribution shifts against the reference window |
| `SLOW` | correct answer, latency spike |
| `ERROR` | raises; the only mode a traditional APM tool would catch |

That last row is the book's thesis in a table. Seven of the eight failures return a clean 200.

Higher-level scenarios in `aiobs.testing.scenarios` compose these into full runs:

```python
from aiobs.testing.scenarios import get

run = get("silent_retry_loop")()
assert detect_step_repetition(run)
```

---

## Writing a test that proves a detector fires

The pattern that matters: build the failure, then assert the detector catches it *and* that a healthy case does not. A detector that fires on everything is not a detector.

```python
def test_groundedness_catches_retrieval_drift(evals, knowledge_base):
    context = knowledge_base["refunds"]

    healthy = MockProvider()
    broken = MockProvider(failure_mode=FailureMode.UNGROUNDED)

    good = evals.scores(healthy.chat("q", context=context).text, context=context, prompt="q")
    bad = evals.scores(broken.chat("q", context=context).text, context=context, prompt="q")

    assert good["groundedness"] > 0.8
    assert bad["groundedness"] < 0.4      # fires
    assert good["groundedness"] > bad["groundedness"]   # and discriminates
```

---

## CI

`.github/workflows/ci.yml` runs two jobs on every push and pull request:

- **test** on Python 3.10, 3.11, and 3.12: ruff, mypy, unit tests, functional tests, coverage
- **simulate**: `aiobs-sim run --all`, uploading `report.html` and `report.json` as artifacts

The simulator exits non-zero on any failure, so a broken listing fails the build. The uploaded HTML report is the fastest way to see which chapter regressed.
