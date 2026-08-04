"""pytest fixtures.

Add this to your ``conftest.py`` and every fixture below is available:

    pytest_plugins = ["aiobs.testing.fixtures"]
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from ..evals import EvalSuite, default_suite
from ..providers import FailureMode, MockProvider
from ..telemetry import configure, get_finished_spans, reset
from .harness import ExampleHarness


@pytest.fixture(autouse=True)
def _isolated_telemetry() -> Iterator[None]:
    """Fresh tracer and empty span buffer for every test.

    ``autouse`` on purpose. A leaked span from a previous test is the
    single most common source of a flaky instrumentation suite.
    """
    configure(service_name="aiobs-pytest", exporter="memory", force=True)
    reset()
    yield
    reset()


@pytest.fixture
def spans():
    """Callable returning the spans finished so far."""
    return lambda: list(get_finished_spans())


@pytest.fixture
def provider() -> MockProvider:
    return MockProvider(seed=1729)


@pytest.fixture
def failing_provider() -> MockProvider:
    return MockProvider(seed=1729, failure_mode=FailureMode.CONFIDENTLY_WRONG)


@pytest.fixture
def harness() -> ExampleHarness:
    return ExampleHarness()


@pytest.fixture
def evals() -> EvalSuite:
    return default_suite()


@pytest.fixture
def knowledge_base() -> dict[str, str]:
    """Small fixed corpus so retrieval examples are deterministic."""
    return {
        "refunds": (
            "Refund extensions apply only to active products purchased after "
            "March 2025. Discontinued products are not eligible."
        ),
        "shipping": (
            "Standard shipping takes three to five business days. Expedited "
            "shipping is next business day for orders placed before 2pm."
        ),
        "warranty": (
            "Hardware carries a twelve month limited warranty from the date "
            "of delivery. Accessories carry ninety days."
        ),
    }
