"""Additional Chapter 8 examples and artifacts.

``chapters.registry.discover()`` imports top-level ``chapters.chNN`` names.
Import the leaf modules here so loading ``chapters.ch08`` registers the
subpackage examples without changing the broader discovery behavior.
"""

from .fully_loaded_cost import fully_loaded_cost_per_acceptable_answer

__all__ = ["fully_loaded_cost_per_acceptable_answer"]
