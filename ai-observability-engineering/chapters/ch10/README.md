# Chapter 10 companion files

| File | Listing | What it is |
|---|---|---|
| `injection_detector.py` | 10.1 | Pattern detector that emits a signal and never the payload |
| `guardrails.py` | 10.2 | Input/output guardrails and the span attributes that audit them |
| `redteam.py` | 10.3 | `run_suite`, which reports pass rate by category |
| `adversarial_cases.yaml` | - | Structural fixtures. **Not an attack corpus.** |
| `owasp_2026.py` | Table 10.1 | Staged 2025 -> 2026 renumbering, pending security SME sign-off |

## Why there is no attack corpus here

`adversarial_cases.yaml` holds instruction-override *shapes* and benign
controls. It holds no working jailbreak, no encoding trick, and nothing
taken from a real incident. This is deliberate: a public companion
repository that ships an operational corpus is a distribution channel for
one, and the book would be handing readers a liability along with a
lesson.

The fixtures still do real work. Half of them are false-positive controls
containing the words "ignore", "previous", "instructions", "developer"
and "above" in ordinary customer sentences. They fail the build if
someone loosens a pattern into a substring match, which is the failure
mode that actually takes a support queue down.

## How to hold your own corpus

Your real corpus is sensitive material and belongs under the same
controls as an incident record, not in the repository your CI logs read
from:

1. **Store it outside this repository** - a private bucket or secrets
   store with object-level access control, not a `private/` directory
   that every CI job can read.
2. **Access-control it separately from source.** Read access to the
   corpus should be a distinct grant from read access to the code;
   commit access must never imply corpus access.
3. **Point CI at a reference, not a copy.** The suite runner takes a
   path, so a job with the right credentials passes its own file and a
   job without them runs these structural fixtures.
4. **Keep provenance per case.** Where it came from, when, and whether it
   is still live, so you can age entries out rather than accumulating
   a corpus nobody can vouch for.
5. **Treat it as reportable.** If it contains real customer prompts, it
   carries the retention and disclosure obligations from Chapters 11
   and 12.

Run the structural suite:

```bash
python -m chapters.ch10.redteam
```
