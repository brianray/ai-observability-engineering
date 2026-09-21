"""The ragas API surface Listing 13.2 depends on, pinned and checked.

``ragas`` has moved its public names more than once, and a printed
listing that calls a renamed class is a listing that does not run. This
module records the surface the chapter relies on, and
``test_ch13_fairness.py`` asserts against the installed package when one
is present, so the build tells you the day the listing goes stale rather
than a reader discovering it.

Verified against **ragas 0.4.3** on 2026-09-21 by reading the published
wheel:

==========================  ===========================================
What the listing uses       Status in 0.4.3
==========================  ===========================================
``ragas.EvaluationDataset``  present, top-level export
``ragas.SingleTurnSample``   present, top-level export
``Faithfulness``             present; ``name`` is ``"faithfulness"``
``ResponseRelevancy``        present; ``name`` is ``"answer_relevancy"``
``llm=`` on a metric         present, via ``MetricWithLLM.llm``
``ragas.llms.LangchainLLMWrapper``  present but **DEPRECATED**
==========================  ===========================================

The one change the manuscript needs: ``LangchainLLMWrapper`` still
imports, but 0.4.3 wraps it in a deprecation shim that says it "will be
removed in a future version" and points at ``llm_factory`` instead. A
listing printed against a deprecated symbol will emit a warning on every
reader's first run and stop working inside the edition's shelf life.

Note the asymmetry worth a sentence in the chapter: the class is
``ResponseRelevancy`` but the result column is ``answer_relevancy``.
Both names in the manuscript are correct, and they are correct because
they refer to different things.
"""

from __future__ import annotations

#: The version this surface was verified against.
VERIFIED_RAGAS_VERSION = "0.4.3"
VERIFIED_ON = "2026-09-21"

#: metric class name -> the column name it produces in the result frame.
METRIC_RESULT_COLUMNS: dict[str, str] = {
    "Faithfulness": "faithfulness",
    "ResponseRelevancy": "answer_relevancy",
}

#: Top-level names the listing imports from ``ragas``.
TOP_LEVEL_IMPORTS: tuple[str, ...] = ("EvaluationDataset", "SingleTurnSample", "evaluate")

#: Import path the listing uses for the LLM wrapper.
LLM_WRAPPER_IMPORT_PATH = "ragas.llms"
LLM_WRAPPER_NAME = "LangchainLLMWrapper"

#: Set when the pinned symbol is deprecated upstream but still importable.
LLM_WRAPPER_DEPRECATED = True
LLM_WRAPPER_REPLACEMENT = "ragas.llms.llm_factory"
