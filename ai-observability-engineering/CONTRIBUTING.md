# Contributing

This repository is the companion to a published book, so the bar is a little different from a normal open-source project: the code has to keep matching the manuscript.

## Ground rules

1. **Every listing in the book is a registered example here.** If you change an example, check whether the corresponding listing needs to change too, and say so in the pull request.
2. **Examples must run offline and deterministically.** No API keys, no network, no wall-clock dependence. Two runs produce identical span counts and token totals.
3. **No attribute outside a declared namespace.** `gen_ai.*` for standardized fields, `eval.*` and `aiobs.*` for this book's. `llm.*` fails the build on purpose.
4. **No payload in telemetry.** Record a reference, not the content.

## Workflow

```bash
python -m pip install -e ".[dev]"
make all          # lint, typecheck, test, sim
```

All four must pass. CI runs the same on Python 3.10, 3.11, and 3.12.

## Adding an example

See [`docs/AUTHORING.md`](docs/AUTHORING.md). In short: one decorated function in `chapters/chNN_*.py`, plus one behavior test in `tests/functional/test_chapter_behavior.py`.

## Reporting a problem

If `aiobs-sim run --all` is red on a clean checkout, that is a bug here, not in your setup. Open an issue with:

- Python version and OS
- The full output of `aiobs-sim run --all --verbose --no-color`
- Whether `pytest tests/unit` also fails

## Changing the semantic conventions

The GenAI conventions are pre-1.0 and move. When they do:

1. Update `SEMCONV_VERSION` and the affected constants in `src/aiobs/semconv.py`
2. Run `make all`
3. Note in the pull request which listings in the manuscript now print different attribute names

Do not chase a spec change by editing attribute strings in the examples. That is what the mapping layer is for.

## Style

- Line length 100, ruff-enforced
- Type hints on public functions
- Docstrings lead with what the code demonstrates, then how
- Comment the non-obvious decision, not the line
- No em dashes
