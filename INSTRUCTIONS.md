# Instructions

Everything you need to run the book's code, and to use the framework in your own project.

---

## 1. Requirements

- Python 3.10 or newer
- No API key, no network, no GPU
- Optional: Docker, if you want telemetry to land in a real backend

## 2. Install

```bash
git clone https://github.com/ai-observability-engineering/ai-observability-engineering.git
cd ai-observability-engineering

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

python -m pip install -e ".[dev]"
```

Verify:

```bash
aiobs-sim --version
aiobs-sim run --chapter 1
```

If `aiobs-sim` is not on your PATH, use `python -m simulator.app` instead. Everything below works with either form.

## 3. First run

```bash
aiobs-sim run --all
```

You should see 17 chapters, 28 examples, and a green summary line. If anything is red, that is a bug in this repository, not in your setup. Open an issue with the output.

```bash
pytest                       # 347 tests
pytest tests/unit            # framework internals only, fast
pytest tests/functional      # every example, every chapter claim
make report                  # writes report.html and report.json
```

## 4. What the simulator does

For each registered example it:

1. Installs a fresh tracer with an in-memory exporter
2. Runs the example
3. Captures every span it emitted
4. Checks each span against the instrumentation contract
5. Records spans, tokens, simulated cost, wall time, and any violations

An example passes only if it raised nothing **and** violated nothing. Instrumentation that emits plausible-looking but non-conformant telemetry fails, which is the point.

### Selecting examples

```bash
aiobs-sim run --all
aiobs-sim run --chapter 10
aiobs-sim run --pillar responsibility
aiobs-sim run --example ch06.output_drift_psi --example ch06.retrieval_drift_incident
aiobs-sim list
aiobs-sim coverage
aiobs-sim scenarios
```

### Output formats

```bash
aiobs-sim run --all                      # coloured terminal report
aiobs-sim run --all --no-color           # for CI logs
aiobs-sim run --all --format json        # machine readable, to stdout
aiobs-sim run --all --format quiet       # one line
aiobs-sim run --all --html report.html   # standalone file, no external assets
aiobs-sim run --all --verbose            # include full tracebacks
aiobs-sim run --all --lenient            # skip semconv and PII enforcement
```

Use `--lenient` while you are mid-refactor and the attribute names are not settled yet. Do not use it in CI.

## 5. Running against a real backend

The examples emit real OpenTelemetry spans. The in-memory exporter is a test affordance, not a limitation.

```bash
pip install ".[otlp]"
docker compose up -d

OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318/v1/traces aiobs-sim run --all
open http://localhost:16686
```

Or in code:

```python
from aiobs import configure

configure(service_name="my-service", exporter="otlp", endpoint="http://localhost:4318/v1/traces")
```

Exporters: `memory` (default), `console`, `otlp`, `none`.

The collector config at `config/otel-collector.yaml` runs two pipelines on purpose:

- **`traces/sampled`** — 10% head sampling, payload attributes stripped. Fine for latency work.
- **`traces/cost`** — unsampled, filtered to spans carrying `aiobs.cost.usd`.

That split is Chapter 2's argument as configuration. A sampled stream cannot be a system of record for spend: sample at 10% and your cost total is wrong by however much the sample happened to miss. Run `aiobs-sim run --example ch02.collector_pipeline_sampling` to see the error size.

## 6. Using the framework in your own project

```bash
pip install ai-observability-engineering
```

### Instrument a model call

```python
from aiobs import configure, llm_span
from aiobs.instrument import set_llm_attributes, set_eval_attributes, set_cost_attributes

configure(service_name="support-assistant", exporter="otlp")

with llm_span(provider="anthropic", model="claude-sonnet-4-5") as span:
    reply = client.messages.create(...)
    set_llm_attributes(
        span,
        provider="anthropic",
        model=reply.model,
        input_tokens=reply.usage.input_tokens,
        output_tokens=reply.usage.output_tokens,
        finish_reason=reply.stop_reason,
    )
    set_cost_attributes(span, cost_usd, tenant="acme", use_case="support")
    set_eval_attributes(span, {"groundedness": 0.91}, evaluator="ragas-v2")
```

### Instrument everything else

```python
from aiobs import Layer, Pillar, observe

@observe(pillar=Pillar.PERFORMANCE, layer=Layer.DATA_AND_RETRIEVAL)
def retrieve(query: str) -> list[str]:
    return vector_store.search(query, k=5)

@observe(pillar=Pillar.ROI, layer=Layer.BUSINESS_AND_OUTCOMES)
def record_resolution(ticket_id: str, resolved: bool) -> None:
    ...
```

Tagging the pillar and layer is what makes coverage reporting possible. Skip it and the framework still works; you just lose the ability to see which pillar nobody is instrumenting.

### Bring your own provider

Implement the protocol and every example works against it unchanged:

```python
from aiobs.providers import ChatResponse, LLMProvider

class AnthropicProvider:
    name = "anthropic"
    model = "claude-sonnet-4-5"

    def chat(self, prompt: str, **kwargs) -> ChatResponse:
        reply = client.messages.create(...)
        return ChatResponse(
            text=reply.content[0].text,
            model=reply.model,
            provider=self.name,
            input_tokens=reply.usage.input_tokens,
            output_tokens=reply.usage.output_tokens,
        )

    def price(self, input_tokens: int, output_tokens: int) -> float:
        return input_tokens / 1000 * 0.003 + output_tokens / 1000 * 0.015

assert isinstance(AnthropicProvider(), LLMProvider)
```

### Bring your own evaluator

```python
from aiobs.evals import Evaluator, register

class LLMJudgeGroundedness(Evaluator):
    name = "groundedness"

    def score(self, output: str, *, context: str | None = None, **kwargs) -> float:
        return judge_model.rate(output, context)

register("llm_judge_groundedness", LLMJudgeGroundedness)
```

Record the eval set version. A score with no version attached is not interpretable six months later, which is the practical form of Chapter 1's third pitfall.

## 7. Pinning the semantic conventions

The GenAI conventions are pre-1.0. Attribute names still move.

`src/aiobs/semconv.py` is the only file that knows the strings. When the spec changes, edit `SEMCONV_VERSION` and the affected constants there; every example and test picks it up. That indirection costs one import and saves a repository-wide find-and-replace.

```python
from aiobs.semconv import SEMCONV_VERSION, GenAI

print(SEMCONV_VERSION)          # 1.37.0
print(GenAI.USAGE_INPUT_TOKENS) # gen_ai.usage.input_tokens
```

## 8. Troubleshooting

**`ModuleNotFoundError: aiobs`**
The package is not installed in editable mode. Run `pip install -e ".[dev]"` from the repository root, or set `PYTHONPATH=src:.`.

**`aiobs-sim: command not found`**
Use `python -m simulator.app` instead, or activate the virtualenv you installed into.

**An example reports `example emitted no spans`**
The tracer was reconfigured after the harness installed it. Call `configure()` once at process start, and never inside an example.

**Violation: `carries non-namespaced attributes ['llm.model']`**
This is the harness doing its job. `llm.*` was never an OpenTelemetry convention. Use `gen_ai.request.model` and friends from `aiobs.semconv.GenAI`, or move the attribute into a prefix you own.

**Violation: `attribute 'x' looks like PII`**
Something wrote a payload into telemetry. Record a reference, not the content: `span.set_attribute("aiobs.risk.evidence_ref", "vault://prompts/1234")`.

**Violation: `records cost but leaves it unattributed`**
`set_cost_attributes` was called without a tenant. Unattributed spend is the ROI failure mode of Part III; the harness treats it as a defect rather than a default.

**Tests pass locally, fail in CI**
Almost always span leakage between tests. Make sure `pytest_plugins = ["aiobs.testing.fixtures"]` is in your `conftest.py`; the autouse fixture resets the tracer between tests.

**Drift detector raises `reference window has zero variance`**
The reference window is a constant. PSI cannot bin a degenerate distribution, and returning a confident zero would be worse than raising. Widen the window or use a metric that actually varies.
