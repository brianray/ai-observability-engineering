"""The langgraph surface Chapters 15 and 17 depend on, pinned and checked.

Verified against **langgraph 1.2.12** / **langgraph-checkpoint 4.2.0** on
2026-09-21, by reading the published wheels and importing them:

===========================================  ==========================
What the listings use                        Status
===========================================  ==========================
``langgraph.graph.StateGraph``                present
``langgraph.graph.END`` / ``START``           present
``StateGraph.add_node`` / ``add_edge``        present
``StateGraph.add_conditional_edges``          present
``StateGraph.set_entry_point``                present (alias for
                                              ``add_edge(START, key)``,
                                              not deprecated)
``StateGraph.compile(checkpointer=...)``      present, first positional
``langgraph.types.interrupt``                 present
``langgraph.types.Command(resume=...)``       present
``langgraph.checkpoint.memory.InMemorySaver`` present (separate
                                              ``langgraph-checkpoint``
                                              distribution)
===========================================  ==========================

``langgraph`` is an OPTIONAL extra. The chapter's instrumentation does
not depend on it: ``agent_graph.py`` runs the same pipeline over plain
callables so the book's telemetry claims are testable in CI without the
dependency tree. The langgraph-backed path exists because Chapter 17's
governance checkpoint needs a real ``interrupt()``, and a book that
describes ``interrupt()`` without ever running it will get it wrong.
"""

from __future__ import annotations

import importlib.util

VERIFIED_LANGGRAPH_VERSION = "1.2.12"
VERIFIED_CHECKPOINT_VERSION = "4.2.0"
VERIFIED_ON = "2026-09-21"

#: module path -> names the listings import from it.
PINNED_IMPORTS: dict[str, tuple[str, ...]] = {
    "langgraph.graph": ("StateGraph", "END", "START"),
    "langgraph.types": ("interrupt", "Command"),
    "langgraph.checkpoint.memory": ("InMemorySaver",),
}

#: Methods Listing 15.1 calls on StateGraph.
PINNED_STATEGRAPH_METHODS: tuple[str, ...] = (
    "add_node",
    "add_edge",
    "add_conditional_edges",
    "set_entry_point",
    "compile",
)


def has_langgraph() -> bool:
    return importlib.util.find_spec("langgraph") is not None
