"""Additional Chapter 5 examples.

``chapters.registry.discover()`` imports top-level ``chapters.chNN*`` names.
Import the leaf modules here so loading ``chapters.ch05`` registers these
examples without changing the broader discovery behavior.
"""

from .cross_service_propagation import cross_service_propagation
from .rag_pipeline_broken import rag_pipeline_broken
from .rag_pipeline_traced import rag_pipeline_traced

__all__ = [
    "cross_service_propagation",
    "rag_pipeline_broken",
    "rag_pipeline_traced",
]
