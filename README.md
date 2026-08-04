# AI Observability Engineering

Companion repository for **_AI Observability Engineering: Operating Intelligent Systems in Production_** (Pearson Addison-Wesley).

Three things live here:

1. **`aiobs`** — a small instrumentation framework built on OpenTelemetry, organized around the book's two structures: the four pillars (Chapter 1) and the five observable layers (Chapter 2).
2. **`aiobs.testing`** — a testing harness for instrumentation. Instrumentation is code, and untested code rots.
3. **`aiobs-sim`** — a simulator that runs every example in the book and reports what each one emitted.

Every listing in the manuscript is a registered example here, and every registered example runs in CI. If a listing in the book stops working, the build fails and names the chapter.

**No API key is required.** Every example runs offline against a seeded mock provider, so results are deterministic and running the book costs nothing.

---

## Quick start

```bash
git clone https://github.com/ai-observability-engineering/ai-observability-engineering.git
cd ai-observability-engineering
python -m pip install -e ".[dev]"

aiobs-sim run --all        # run every example in the book
pytest                     # run the full test suite
```

Expected output from `aiobs-sim run --all`:

```
Chapter 01  The Observability Imperative for AI Systems   [Part I: Foundations of AI Observability]
  PASS  traditional_vs_llm_span           Listing 1.1     2 spans      63 tok  $ 0.000000    1.4 ms
  PASS  green_dashboard_wrong_answer      -               1 spans      31 tok  $ 0.000000    0.6 ms
...
28/28 examples passed  |  205 spans (160 LLM)  |  5,758 tokens  |  $0.235405 simulated  |  53 ms
```

---

## The 60-second version

```python
from aiobs import MockProvider, capture, llm_span, default_suite
from aiobs.instrument import set_eval_attributes, set_llm_attributes
from aiobs.testing import assert_llm_span, assert_semconv_compliant

context = "Refund extensions apply only to active products purchased after March 2025."
question = "Is the discontinued model still eligible?"

with capture() as spans:
    provider = MockProvider()
    reply = provider.chat(question, context=context)

    with llm_span(provider=provider.name, model=provider.model) as span:
        set_llm_attributes(
            span,
            provider=provider.name,
            model=reply.model,
            input_tokens=reply.input_tokens,
            output_tokens=reply.output_tokens,
        )
        scores = default_suite().scores(reply.text, context=context, prompt=question)
        set_eval_attributes(span, scores, evaluator="heuristic-v1")

assert_llm_span(spans[0])          # required gen_ai.* attributes are present
assert_semconv_compliant(spans[0]) # no attribute outside a declared namespace
```

---

## Attribute namespaces

The single rule this repository enforces everywhere: **every attribute belongs to a namespace, and you know which kind.**

| Namespace | Status | Owner | Examples |
|---|---|---|---|
| `gen_ai.*` | Standardized | OpenTelemetry GenAI semantic conventions | `gen_ai.request.model`, `gen_ai.usage.input_tokens` |
| `http.*`, `db.*`, `service.*` … | Standardized | OpenTelemetry | `http.response.status_code` |
| `eval.*` | **Not standardized** | This book | `eval.groundedness_score` |
| `aiobs.*` | **Not standardized** | This book | `aiobs.cost.usd`, `aiobs.pillar` |
| anything else | Rejected | — | `llm.model`, `my_attribute` |

`llm.*` was never a convention. Early drafts of this book used it; the tests now fail the build on it. See `aiobs/semconv.py`.

The conventions are pre-1.0 and the attribute names are still moving. `SEMCONV_VERSION` in `aiobs/semconv.py` pins the version this repository was built against. Change it there, nowhere else.

---

## Repository layout

```
src/aiobs/                   the framework
  semconv.py                 pinned attribute names; the thin mapping layer
  telemetry.py               tracer setup, exporters, in-memory span capture
  instrument.py              @observe decorator, llm_span(), attribute helpers
  pillars.py                 four pillars, five layers, four scopes
  providers/                 LLMProvider protocol + the offline mock
  evals/                     evaluator interface, heuristics, suite runner
  cost.py                    price book, cost ledger, ROI arithmetic
  drift.py                   PSI and two-sample KS
  risk.py                    OWASP LLM Top 10 detectors
  agents.py                  MAST failure taxonomy, agent run analysis
  testing/                   THE HARNESS: assertions, fixtures, scenarios

chapters/                    one module per chapter, 17 of them
  registry.py                @example decorator + coverage reporting
  ch01_foundations.py        ... through ch17_accountability.py

simulator/                   the simulation app
  runner.py                  executes examples through the harness
  report.py                  terminal, JSON, and standalone HTML output
  app.py                     the aiobs-sim CLI

tests/
  unit/                      framework internals, 96 tests
  functional/                every example, every chapter's claims, 251 tests

config/otel-collector.yaml   two-pipeline collector config (sampled + unsampled cost)
docker-compose.yml           optional local Jaeger + collector
```

---

## The testing harness

Two entry points, same contract.

**pytest style:**

```python
from aiobs.testing import ExampleHarness

def test_my_pipeline():
    result = ExampleHarness().run(my_pipeline)
    assert result.ok, result.violations
    assert result.llm_span_count == 1
```

**unittest style:**

```python
from aiobs.testing import ObservabilityTestCase

class TestMyPipeline(ObservabilityTestCase):
    def test_emits_a_valid_llm_span(self):
        with self.capture_spans():
            my_pipeline("hello")
        self.assertLLMSpanCount(1)
        self.assertAllSpansCompliant()
        self.assertSingleTrace()
        self.assertNoPII()
```

Add the fixtures to your own `conftest.py`:

```python
pytest_plugins = ["aiobs.testing.fixtures"]
```

That gives you `provider`, `failing_provider`, `harness`, `evals`, `spans`, `knowledge_base`, and an autouse fixture that resets the tracer between tests. Use it. A span leaked from a previous test is the most common cause of a flaky instrumentation suite.

### Assertions

| Assertion | Catches |
|---|---|
| `assert_llm_span` | model-invoking span missing model or token counts |
| `assert_genai_span` | any GenAI span missing operation or provider |
| `assert_semconv_compliant` | attributes outside a declared namespace |
| `assert_no_pii` | emails, SSNs, card numbers in span attributes |
| `assert_same_trace` | broken context propagation across async or thread boundaries |
| `assert_cost_attributed` | cost recorded but left unattributed |
| `assert_evaluated` | missing eval scores, or a hallucination score over threshold |
| `assert_parent_of`, `assert_span_count`, `assert_ok`, `assert_error` | trace structure |

Tool and agent spans are checked with `assert_genai_span`, not `assert_llm_span`. An `execute_tool` span has no model, and inventing `model="n/a"` to satisfy a linter makes the trace harder to read.

### Failure scenarios

`aiobs.testing.scenarios` ships reproducible versions of the failures the book keeps returning to:

```bash
aiobs-sim scenarios
```

| Key | Failure | Detected by |
|---|---|---|
| `silent_retry_loop` | Uptime 99.99%, error rate 0.0%, $47,000 bill | `agents.detect_step_repetition` |
| `confidently_wrong` | Fluent, well formed, factually false | `evals.HallucinationEvaluator` |
| `ungrounded_rag` | A document update quietly breaks grounding | `evals.GroundednessEvaluator` |
| `no_termination` | MAST FM-1.5, runs to the step ceiling | `agents.detect_missing_termination` |
| `unverified_output` | MAST FM-3.2, nobody checked the result | `agents.detect_missing_verification` |

---

## The simulator

```bash
aiobs-sim run --all                              # everything
aiobs-sim run --chapter 6 --verbose              # one chapter, with tracebacks
aiobs-sim run --pillar risk                      # one pillar
aiobs-sim run --example ch01.traditional_vs_llm_span
aiobs-sim run --all --html report.html           # standalone HTML report
aiobs-sim run --all --format json                # machine readable
aiobs-sim list                                   # every registered example
aiobs-sim coverage                               # pillar / layer / chapter gaps
```

Exit code is `0` when every selected example passes, `1` otherwise, so it drops straight into CI.

The coverage report shows **declared** against **observed**: a pillar can be declared on an example and never appear on a span, which means the example talks about the pillar without instrumenting it. The gap between those two columns is the interesting part.

### Running against a real pipeline

```bash
docker compose up -d
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318/v1/traces aiobs-sim run --all
open http://localhost:16686
```

The collector config in `config/otel-collector.yaml` deliberately runs two pipelines: traces sampled at 10%, cost spans unsampled. That is Chapter 2's argument in a config file. A sampled stream is fine for latency percentiles and useless as a system of record for spend.

---

## Referencing this repository from the book

Each chapter cites the module that implements its listings:

| Chapter | Module | Key APIs |
|---|---|---|
| 1 | `chapters/ch01_foundations.py` | `llm_span`, `set_llm_attributes`, `set_eval_attributes` |
| 2 | `chapters/ch02_anatomy.py` | `Layer`, `observe`, `CostLedger` |
| 3 | `chapters/ch03_signals.py` | `Scope`, `GenAI.CONVERSATION_ID` |
| 4 | `chapters/ch04_instrumentation.py` | `llm_span`, `Operation.EXECUTE_TOOL` |
| 5 | `chapters/ch05_performance.py` | percentile helpers, throughput attributes |
| 6 | `chapters/ch06_drift.py` | `drift.population_stability_index`, `drift.kolmogorov_smirnov` |
| 7 | `chapters/ch07_cost_accounting.py` | `CostLedger`, `price_call`, `UnknownModelError` |
| 8 | `chapters/ch08_cost_engineering.py` | routing, cache accounting |
| 9 | `chapters/ch09_roi.py` | `roi`, `cost_per_outcome` |
| 10 | `chapters/ch10_llm_security.py` | `risk.scan`, `risk.detect_system_prompt_leak`, `OwaspLLM` |
| 11 | `chapters/ch11_compliance.py` | NIST AI RMF / EU AI Act / ISO 42001 crosswalk |
| 12 | `chapters/ch12_audit.py` | hash-chained audit records |
| 13 | `chapters/ch13_fairness.py` | cohort quality parity |
| 14 | `chapters/ch14_human_oversight.py` | `Aiobs.HUMAN_REVIEW_OUTCOME` |
| 15 | `chapters/ch15_agent_tracing.py` | `AgentRun`, handoff depth |
| 16 | `chapters/ch16_agent_cost.py` | `agents.classify`, `agents.failure_vector` |
| 17 | `chapters/ch17_accountability.py` | delegation chain attributes |

Cite it in the manuscript like this:

> The complete, runnable version of this listing is in the companion repository at `chapters/ch04_instrumentation.py`. Every listing in this book has a counterpart there, pinned to the library and specification versions current at the time of writing.

---

## Documentation

- **[`docs/INSTRUCTIONS.md`](docs/INSTRUCTIONS.md)** — setup, first run, troubleshooting, using the framework in your own project
- **[`docs/TESTING.md`](docs/TESTING.md)** — the harness in depth, what each assertion catches, how to test instrumentation you already have
- **[`docs/AUTHORING.md`](docs/AUTHORING.md)** — adding a chapter example, the contract it has to meet
- **[`CONTRIBUTING.md`](CONTRIBUTING.md)** — pull request expectations

---

## A note on the numbers

Every figure the simulator prints is **simulated**, produced by a seeded offline mock. The token counts, latencies, and dollar amounts are internally consistent and reproducible; they are not measurements of any real system, and the price book in `aiobs/cost.py` is illustrative. Refresh it before quoting a cost.

The heuristic evaluators in `aiobs/evals/heuristics.py` exist so the examples run deterministically without a judge model. **Do not ship them as production quality gates.** Swap the implementation, keep the interface.

Framework citations in `chapters/ch11_compliance.py` are illustrative. Verify current article and control numbers against the source text before relying on them.

---

## License

MIT. See [`LICENSE`](LICENSE).
