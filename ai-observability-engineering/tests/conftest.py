"""Shared pytest configuration.

``aiobs.testing.fixtures`` is loaded as a plugin, which gives every test an
isolated tracer and an empty span buffer. Do the same in your own project:
a span leaked from a previous test is the most common cause of a flaky
instrumentation suite.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "src", ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

pytest_plugins = ["aiobs.testing.fixtures"]
