"""Additional Chapter 6 examples and helpers.

``chapters.registry.discover()`` only imports top-level ``chapters.chNN*``
modules and packages. Import the leaf example module here so loading
``chapters.ch06`` registers the new examples without disturbing the
existing ``chapters.ch06_drift`` module.
"""

from .alerting import AlertMetrics, evaluate_alert_tier, load_alerting_rules
from .drift_detector import embedding_drift_neighbors

__all__ = [
    "AlertMetrics",
    "embedding_drift_neighbors",
    "evaluate_alert_tier",
    "load_alerting_rules",
]
