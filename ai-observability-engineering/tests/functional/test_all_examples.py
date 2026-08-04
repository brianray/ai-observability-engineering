"""Functional: every registered example runs and is correctly instrumented.

This is the test that keeps the manuscript honest. Every listing in the
book is a registered example; if a listing stops working, this fails, and
the failure names the chapter.
"""

import pytest

from aiobs.testing import ExampleHarness
from chapters.registry import CHAPTER_TITLES, all_examples, coverage, for_chapter

EXAMPLES = all_examples()


@pytest.mark.parametrize("spec", EXAMPLES, ids=lambda s: s.id)
def test_example_runs_and_is_instrumented(spec):
    result = ExampleHarness().run(spec.func, name=spec.id, expect_error=spec.expect_error)
    assert result.error is None, f"{spec.id} raised: {result.error!r}"
    assert not result.violations, f"{spec.id} violations: {result.violations}"


@pytest.mark.parametrize("spec", EXAMPLES, ids=lambda s: s.id)
def test_example_emits_spans(spec):
    result = ExampleHarness().run(spec.func, name=spec.id)
    assert result.spans, f"{spec.id} produced no telemetry"


@pytest.mark.parametrize("spec", EXAMPLES, ids=lambda s: s.id)
def test_example_is_deterministic(spec):
    """Two runs, identical results.

    An example whose output moves between runs cannot be quoted in a
    book, because the number in the manuscript would be wrong by the time
    a reader ran it.
    """
    first = ExampleHarness().run(spec.func, name=spec.id)
    second = ExampleHarness().run(spec.func, name=spec.id)
    assert len(first.spans) == len(second.spans)
    assert first.total_tokens == second.total_tokens


@pytest.mark.parametrize("chapter", sorted(CHAPTER_TITLES))
def test_every_chapter_has_at_least_one_example(chapter):
    assert for_chapter(chapter), f"chapter {chapter} has no runnable example"


def test_every_pillar_is_exercised():
    assert coverage()["uncovered_pillars"] == []


def test_listing_numbers_are_unique():
    listings = [s.listing for s in EXAMPLES if s.listing]
    assert len(listings) == len(set(listings)), "two examples claim the same listing number"


def test_listing_numbers_match_their_chapter():
    for spec in EXAMPLES:
        if spec.listing:
            assert spec.listing.split(".")[0] == str(spec.chapter), (
                f"{spec.id} claims Listing {spec.listing}"
            )


def test_example_ids_are_unique():
    ids = [s.id for s in EXAMPLES]
    assert len(ids) == len(set(ids))
