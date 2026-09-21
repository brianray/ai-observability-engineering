# Print readiness: repository vs. manuscript

**Pass run:** 2026-09-21
**Scope:** the consolidated repo-sync work order covering every REPO TODO
callout (Chapters 8, 10-17), the repo-facing editorial threads from
Chapters 4-17, and the naming-convention question that was blocking them.
**Suite at end of pass:** 641 passed, 6 skipped, lint clean.

---

## The headline

Three things in this report change what goes on the page, and they are
the ones to read first.

1. **Chapter 8 was shipping a live pricing and routing bug.** The large
   tier routed to Sonnet, and the Haiku row carried Haiku 3.5's prices.
   Both are fixed. **The chapter-opening cost figure moves from
   $0.010500 to $0.052500**, and Table 8.1 has to move with it.
2. **`claude-opus-4-1`, the model Table 8.1 uses for its Large tier, is
   retired on the first-party API.** The price book is correct and the
   model is not orderable except on Bedrock and Google Cloud. This is a
   tiering decision for the author, not a code fix.
3. **Two figures in Chapter 15 are still illustrator specs.** No amount
   of repository work clears that; it blocks print on its own.

Everything else is either fixed, staged for a named reviewer, or listed
below as a question.

---

## Chapter by chapter

"Consistent" below means the companion code exists at the path the
manuscript cites, implements what the chapter describes, and is covered
by tests that assert the specific claims the REPO TODO asked for.

| Ch | Module path | Consistent? | Note |
|---|---|---|---|
| 1 | `chapters/ch01_foundations.py` | Yes | Not in this pass's scope. Registered, runs, tests pass. |
| 2 | `chapters/ch02_anatomy.py` | Yes | As above. |
| 3 | `chapters/ch03_signals.py` | **Changed** | Now emits its log signal through the shared `aiobs.logging` logger, so Chapters 3 and 10 share one logging path as the Chapter 10 TODO required. |
| 4 | `chapters/ch04_instrumentation.py` | Yes, with one prose fix | `stream_options={"include_usage": True}` verified against the pinned `openai==1.109.1`. The TTFT claim needs qualifying; see below. |
| 5 | `chapters/ch05_performance.py`, `chapters/ch05/` | Yes | The collector + Jaeger item the chapter still lists as open is in fact satisfied. See below. |
| 6 | `chapters/ch06_drift.py`, `chapters/ch06/` | Yes | Not in this pass's scope. |
| 7 | `chapters/ch07_cost_accounting.py` | Yes | Not in this pass's scope. |
| 8 | `chapters/ch08_cost_engineering.py`, `chapters/ch08/` | **Was not** | Real routing bug and real price error, both fixed. Manuscript numbers must follow. |
| 9 | `chapters/ch09_roi.py` | Yes | Not in this pass's scope. |
| 10 | `chapters/ch10_llm_security.py`, `chapters/ch10/` | **Was not** | Detector, guardrails, red-team suite and fixtures did not exist. Built. OWASP 2026 remap staged, not applied. |
| 11 | `chapters/ch11_compliance.py`, `chapters/ch11/` | **Was not** | Compliance tagging, tail-sampling fragment and gap analysis did not exist. Built. |
| 12 | `chapters/ch12_audit.py`, `chapters/ch12/` | **Was not** | Audit logger, append-only stores, custody and dossier assembly did not exist. Built. |
| 13 | `chapters/ch13_fairness.py`, `chapters/ch13/` | **Was not** | RAG eval, fairness gauges and `fairness_alerts.yaml` did not exist. Built. |
| 14 | `chapters/ch14_human_oversight.py`, `chapters/ch14/` | **Was not** | HITL router, feedback capture and dashboard artifacts did not exist. Built. One namespace conflict with Listing 14.1; see below. |
| 15 | `chapters/ch15_agent_tracing.py`, `chapters/ch15/` | **Was not** | Graph, handoff logging and health map did not exist. Built. Figures still outstanding. |
| 16 | `chapters/ch16_agent_cost.py`, `chapters/ch16/` | **Was not** | Tool wrapper, loop breaker and memory metrics did not exist. Built. |
| 17 | `chapters/ch17_accountability.py`, `chapters/ch17/` | **Was not** | All three listings were absent, as the work order predicted. Built, and one of the chapter's claims needs revising; see below. |

### On the naming convention

Settled and not re-opened: `chapters/chNN_topic.py` is the module the
manuscript cites, and it is what the registry discovers. Where a chapter
needs several concerns, the repository's own established pattern is a
`chapters/chNN/` support package alongside it, which Chapters 5, 6 and 8
already used before this pass. Chapters 10 through 17 now follow the same
shape. Chapter 17 re-exports all three of its listings from
`chapters/ch17_accountability.py`, so the manuscript's single-path
citation resolves and a reader can import everything from one place.

---

## Needs the author's decision

**1. Chapter 8's cost figures moved.** Fixing `LARGE_MODEL` changes the
worked example from **$0.010500 to $0.052500** for 1,500 input / 400
output tokens. Every derived figure in the chapter moves with it. The
repository computes this from `pricing.json`, so the code is right either
way; the printed numbers are the open item.

**2. Table 8.1's Large tier names a retired model.** Per the published
pricing page on 2026-09-21, `claude-opus-4-1` is retired except on
Bedrock and Google Cloud. A cost-engineering chapter whose worked example
routes to an unorderable model will read as dated on day one. Options,
in the order I would consider them:
  - Re-tier onto current models (for example Haiku 4.5 / Sonnet 5 /
    Opus 4.5 or later) and re-run the numbers. Cleanest, and the price
    book regenerates the Prometheus rules automatically.
  - Keep the current tiering and add a sentence dating the price book.
  - Keep it and note the Bedrock/Vertex availability explicitly.

This is a book-positioning call, so I have not made it.

**3. What to do with the REPO TODO boxes (Section 10.1).** They have now
served their purpose. The work order recommends striking them in favour
of a single "Companion code: `chapters/chNN_topic.py`" pointer, with the
alternative being a "Verified against commit `<sha>` on `<date>`" note.
The work order is explicit that this is the author's call, so it is
flagged rather than done.

**4. Listing 14.1's `hitl.*` attribute prefix is not a legal namespace in
this repository.** `test_semconv_conformance.py` rejects any attribute
outside the declared prefixes, and a bare `hitl.` is not one of them. The
repository's own rule (AUTHORING.md) is that book-specific attributes
live under `aiobs.`. The code therefore emits `aiobs.hitl.routed`,
`aiobs.hitl.reason`, `aiobs.hitl.queue` and `aiobs.hitl.confidence`.
**Listing 14.1 needs the same prefix**, or the repository needs a new
declared namespace. I took the first reading because it is what the
book's own stated rule says, but the manuscript currently disagrees with
the code and one of them has to move.

---

## Needs a named SME, not the author

**Chapter 10, the OWASP 2025 to 2026 renumbering.** Staged, not applied,
exactly as the work order directs. `chapters/ch10/owasp_2026.py` carries
the full mapping, the `System Prompt Leakage` to `Hidden Context
Exposure` rename and its widened scope, the methodology note about the
75/25 consensus-and-incident weighting, and the scope boundary against
the separate Agentic list. **Nothing imports it**; importing it changes
no behavior. `aiobs.risk.OwaspLLM` still encodes the 2025 numbering and
every example still emits 2025 ids. The SME REVIEW boxes in Sections
10.2, 10.3, 10.4 and 10.11 remain the routing mechanism.

One caveat I want on the record: **I could not verify the 2026 mapping
against a primary source.** Both `genai.owasp.org` and `owasp.org` are
unreachable through this environment's egress proxy. The mapping in that
module is transcribed from the review packet and is marked as such in its
docstring. The SME should verify it against the published edition before
anyone flips it.

**Chapter 13, the seven fairness SME boxes.** Untouched, as instructed.
Threshold-setting governance, the Table 13.5 first-30-days timeline, and
the case-study specifics are all still routed to the fairness co-author.
Worth repeating the reviewer's own question: whether four weeks is
realistic for stakeholder alignment in a credit or employment context is
a governance question, and nothing in the repository can answer it.

**Chapter 11, the EU AI Act timeline.** Verified as accurate and carried
forward without second-guessing, per the work order. It is now encoded as
testable data in `chapters/ch11/eu_ai_act_timeline.py`, including the
part readers most often get wrong: the Digital Omnibus defers the
high-risk obligations and does **not** touch Article 50 transparency,
GPAI provider obligations, or the Article 5 prohibitions. The regulatory
co-author's final sign-off against the enacted text is still outstanding.

---

## Blocks print regardless of repository state

**Figures 15.1 and 15.2 are still illustrator specs.** They are
panel-by-panel placeholder boxes in the manuscript, not finished art.
Not a repository task, recorded here because it gates the print date on
its own.

---

## Corrections to specific manuscript claims

**Chapter 4, TTFT.** The chapter says time-to-first-token is "specified
from the server's perspective". That is now incomplete. The current
conventions define **both**: `gen_ai.server.time_to_first_token` and
`gen_ai.client.operation.time_to_first_chunk`, the latter described as
measured "from when the client issues the generation request to when the
first chunk is received in the response stream". The book's own
`measure_ttft` measures client-side, so the client metric is the one that
matches the code. The sentence needs qualifying.

**Chapter 16, the tool-spans citation.** The open question a prior
reviewer raised is answered. The GenAI conventions have moved to
`open-telemetry/semantic-conventions-genai` (the old path now serves a
"Moved" stub). There is **no separate tool-spans page**:
`gen-ai-tool-spans.md` is a 404. The execute-tool span is defined on the
**model** spans page, `docs/gen-ai/gen-ai-spans.md#execute-tool-span`,
and the agent-spans page carries only a cross-reference to it. Table
16.1's citation should point at the model spans page. Both
`gen_ai.operation.name = "execute_tool"` and `gen_ai.tool.name` are
unchanged and correct, and `gen_ai.tool.name` is `Required` on that span.
The spec's span-name template is `execute_tool {gen_ai.tool.name}`, which
the code now follows and a test pins.

**Chapter 13, Listing 13.2.** Verified against `ragas` 0.4.3.
`EvaluationDataset`, `SingleTurnSample`, `Faithfulness`,
`ResponseRelevancy`, the `llm` argument, and the result column names
`"faithfulness"` and `"answer_relevancy"` all still hold. One change is
needed: **`LangchainLLMWrapper` is deprecated upstream**. It still
imports, but 0.4.3 wraps it in a shim warning it "will be removed in a
future version" and pointing at `llm_factory`. A listing printed against
a deprecated symbol warns on every reader's first run. Worth one sentence
in the chapter: the class is `ResponseRelevancy` while the column is
`answer_relevancy`, and both names are correct because they refer to
different things.

**Chapter 17, the responsibility chain across a graph boundary.** This
one is a genuine correction rather than a citation fix. A langgraph node
runs in its own copied context, so a `ContextVar` mutation made inside a
node is discarded when the node returns. The chain therefore does **not**
propagate back out of a graph node, for the same reason it does not cross
a thread-pool boundary. Across a node boundary it has to travel in the
graph state, which is also what the checkpointer persists. The code does
this and the suite keeps it as an explicit test alongside the
thread-pool negative case. If Section 17.3 currently implies the
`ContextVar` alone is sufficient inside a graph, it needs revising.

**Chapter 5, the "still open items" caveat.** The chapter body flags the
collector and Jaeger work as open. It is not. `docker-compose.yml` brings
the collector up alongside Jaeger, mounts the config the repo actually
ships, publishes the ports the README tells readers to use, and both
pipelines export to services the compose file defines. There are now
tests asserting each of those, because "the file exists" is how a broken
quickstart ships. The caveat can come out.

**Top-level README, test count.** Claimed 347 tests. Actual was 112 at
the start of this pass and 641 at the end. Corrected.

**Top-level README, sample simulator output.** The quoted run shows
`28/28 examples passed | 210 spans | 5758 tokens | $0.235405 simulated`.
The actual output is `39/39 examples passed | 240 spans (165 LLM) |
6158 tokens | $900.236170 simulated`. I confirmed this is **pre-existing
drift and not caused by this pass**: `main` produces the identical
figures. Left as found, because the sample block is illustrative prose
rather than a claim the code contradicts, but it should be refreshed
before print, and the $900 figure is startling enough in a cost chapter's
companion README to deserve a glance at which example produces it.

---

## What I could not verify from this environment

Stated plainly so nobody takes silence for confirmation.

- **The OWASP 2026 edition.** Egress blocked to both `owasp.org` and
  `genai.owasp.org`. The staged mapping is transcribed, not verified.
- **`promtool`.** Not installable here (the distro mirror 404s and the
  GitHub releases host returns 403). The Prometheus rule files are
  validated structurally by `tests/support/prometheus.py`, which runs
  everywhere, and the real `promtool` check runs in CI. The three
  promtool-gated tests skip locally.
- **Live Anthropic pricing** was verified against the published pricing
  documentation, which was reachable. `www.anthropic.com` was not.

---

## What changed in the repository

**Fixed defects**

- `chapters/ch08/model_router.py`: `LARGE_MODEL` pointed at
  `claude-sonnet-4-5`, the Mid tier. Now `claude-opus-4-1`. Every
  "large model" estimate had been under-reported by the Opus-to-Sonnet
  ratio. `MID_MODEL` added so the three tiers are named.
- `chapters/ch08/pricing.json`: the `claude-haiku-4-5` entry carried
  0.80 / 0.08 / 4.00, which is exactly Claude Haiku **3.5**'s row. The
  correct rates are 1.00 / 0.10 / 5.00. Sonnet 4.5 and Opus 4.1 were
  already right. `retrieved_on` and a real source URL updated.
- `chapters/ch08/dashboard_rules.yml` is now generated from
  `pricing.json` by `chapters/ch08/pricing_rules.py`, with a test that
  fails when the checked-in file is not the generator's output. The
  previous hand-maintained file had drifted silently, which is how a
  dashboard prices traffic off a stale table with nothing going red.
- `pyproject.toml`: `scipy==1.18.1` requires Python 3.12+, while the
  project declares `requires-python >= 3.10` and ships 3.10 and 3.11
  classifiers. `pip install -e .` failed outright on 3.11. Now behind
  environment markers, so the declared floor is true again.

**New companion code** (Chapters 10-17), each with a `chapters/chNN/`
package, unit tests asserting the specific claims the REPO TODO listed,
and a README where the chapter needed operator guidance. Highlights worth
knowing about:

- `src/aiobs/logging.py`, one structured logger shared by Chapters 3 and
  10, which **refuses** field values long enough to be a payload rather
  than trusting every call site to remember.
- Chapter 10's `adversarial_cases.yaml` contains structural shapes and
  benign controls only. Five of the twelve are false-positive controls
  containing "ignore", "previous", "instructions", "developer" and
  "above" in ordinary customer sentences, so loosening a pattern into a
  substring match fails the build. `chapters/ch10/README.md` documents
  holding a real corpus under separate access control.
- Chapter 12's `verify_chain` is a reference solution in its own module
  and is deliberately **not** a method on `AuditLogger`, so Exercise 12.1
  stays an exercise. A test asserts that.
- Chapter 12's S3 backend **raises on construction** if handed
  `GOVERNANCE` mode, because in GOVERNANCE a privileged principal can
  delete the record the chain is vouching for, which makes the chapter's
  claim false rather than merely weaker.
- Chapter 16's `extra_breakers.py` holds Exercise 16.3's elapsed-time and
  cost breakers, kept out of the printed listings and out of the
  package's `__all__`, with a test asserting that.

**New drift guards.** `tests/unit/test_pinned_external_surfaces.py`
checks the installed `openai`, and the OTel convention strings the book
emits, against what the manuscript was written against. The `ragas` and
`langgraph` surfaces have equivalents in their chapters. These do not
touch the network; they fail the build with the chapter named when a
dependency moves.

**CI.** Now runs the full suite and lint rather than unit tests only,
validates the Chapter 13 and 14 rule files with `promtool`, and exercises
the optional extras in a separate `continue-on-error` job so a `langgraph`
or `ragas` release cannot take the main build down while still surfacing
a stale listing.

---

## Not a repository task, recorded so it is not lost

**Composite case studies (Section 10.5).** Every industry case study from
Chapter 4 onward is a composite: generic industry description, no company
name, no real product, no verbatim client data. This has been confirmed
chapter by chapter through Chapter 17. A single front-matter methodology
note stating it once would be cleaner than the current per-chapter SME
flags. Front-matter edit, not a code change.
