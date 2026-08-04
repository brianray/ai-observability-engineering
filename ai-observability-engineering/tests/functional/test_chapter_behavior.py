"""Functional: the claims each chapter makes, asserted.

The tests above prove the examples run. These prove they demonstrate what
the chapter says they demonstrate. If a chapter's argument stops being
true of its own code, that is the bug worth catching.
"""

import pytest

from aiobs.semconv import Aiobs, Eval, GenAI
from aiobs.testing import ExampleHarness, llm_spans, spans_named
from chapters.registry import get


def _run(example_id: str):
    spec = get(example_id)
    result = ExampleHarness().run(spec.func, name=spec.id)
    assert result.ok, result.violations or result.error
    return result


# --- Chapter 1 -------------------------------------------------------- #

def test_ch01_llm_span_carries_what_the_web_span_cannot():
    result = _run("ch01.traditional_vs_llm_span")
    web = spans_named(result.spans, "GET /api/answer")[0]
    llm = llm_spans(result.spans)[0]
    web_attrs, llm_attrs = dict(web.attributes), dict(llm.attributes)

    assert "http.response.status_code" in web_attrs
    assert GenAI.REQUEST_MODEL not in web_attrs
    assert Eval.HALLUCINATION_SCORE not in web_attrs
    # The four lines the chapter is really about.
    for attribute in (
        GenAI.USAGE_INPUT_TOKENS,
        GenAI.USAGE_OUTPUT_TOKENS,
        Eval.HALLUCINATION_SCORE,
        Eval.GROUNDEDNESS_SCORE,
    ):
        assert attribute in llm_attrs


def test_ch01_green_dashboard_hides_a_wrong_answer():
    """Status 200, latency normal, and only the eval catches it."""
    result = _run("ch01.green_dashboard_wrong_answer")
    payload = result.returned
    assert payload["status_code"] == 200
    assert payload["latency_s"] < 0.2
    assert payload["would_apm_catch_it"] is False
    assert payload["caught_by_pillar"] == "responsibility"
    assert payload["scores"]["groundedness"] < 0.5


# --- Chapter 2 -------------------------------------------------------- #

def test_ch02_trace_spans_all_five_layers():
    result = _run("ch02.five_layers_one_trace")
    observed = result.layers_covered()
    assert len(observed) == 5, f"only reached {sorted(observed)}"


def test_ch02_sampling_destroys_the_cost_total():
    """Latency percentiles survive sampling. Totals do not."""
    payload = _run("ch02.collector_pipeline_sampling").returned
    assert payload["relative_error"] > 0.0
    assert payload["true_total_usd"] > 0


# --- Chapter 5 and 6 -------------------------------------------------- #

def test_ch05_mean_latency_hides_the_tail():
    payload = _run("ch05.latency_distribution").returned
    assert payload["p99_ms"] > payload["p50_ms"]
    assert payload["tail_hidden_by_mean"] is True


def test_ch06_drift_detectors_agree_on_a_real_shift():
    payload = _run("ch06.output_drift_psi").returned
    assert payload["both_agree"] is True
    assert payload["results"]["psi"]["stable"]["verdict"] == "stable"


def test_ch06_retrieval_incident_moves_grounding_not_latency():
    """Chapter 1's case study: the failure is invisible to APM."""
    payload = _run("ch06.retrieval_drift_incident").returned
    assert payload["latency_changed"] is False
    assert payload["error_rate_changed"] is False
    assert payload["mean_groundedness_after"] < payload["mean_groundedness_before"] - 0.2
    assert payload["verdict"] == "significant"


# --- Chapter 7 to 9 --------------------------------------------------- #

def test_ch07_every_llm_span_carries_attributed_cost():
    result = _run("ch07.attributed_cost_ledger")
    costed = [s for s in result.spans if Aiobs.COST_USD in dict(s.attributes)]
    assert costed
    for span in costed:
        assert dict(span.attributes)[Aiobs.COST_TENANT] != "unattributed"


def test_ch07_rollups_sum_to_the_total():
    payload = _run("ch07.attributed_cost_ledger").returned
    assert sum(payload["by_tenant"].values()) == pytest.approx(payload["total_usd"], rel=1e-6)
    assert sum(payload["by_use_case"].values()) == pytest.approx(payload["total_usd"], rel=1e-6)


def test_ch08_routing_saves_money():
    payload = _run("ch08.model_routing_savings").returned
    assert payload["routed_usd"] < payload["baseline_usd"]
    assert payload["saving_fraction"] > 0


def test_ch08_cache_hits_are_free_but_still_traced():
    payload = _run("ch08.cache_hit_accounting").returned
    assert payload["cache_hits"] > 0
    assert payload["billed_calls"] < payload["requests"]


def test_ch09_roi_chain_is_explicit():
    payload = _run("ch09.cost_per_resolution").returned
    assert payload["cost_per_resolution_usd"] > 0
    assert set(payload["assumptions"]) == {
        "minutes_saved_per_resolution",
        "loaded_hourly_rate_usd",
    }


# --- Chapter 10 to 12 ------------------------------------------------- #

def test_ch10_injection_is_blocked_before_inference():
    result = _run("ch10.prompt_injection_signal")
    payload = result.returned
    assert payload["blocked_before_inference"] >= 2
    flagged = [s for s in result.spans if dict(s.attributes).get(Aiobs.RISK_INJECTION_DETECTED)]
    assert flagged
    for span in flagged:
        # The signal is on the span. The payload is not.
        assert "ignore" not in str(dict(span.attributes)).lower()


def test_ch10_leak_detector_distinguishes_leaked_from_clean():
    payload = _run("ch10.system_prompt_leak").returned
    assert payload["detected"] == {"leaked": True, "clean": False}


def test_ch11_every_control_has_evidence():
    payload = _run("ch11.control_crosswalk").returned
    assert payload["unevidenced_controls"] == []
    assert payload["controls"] >= 4


def test_ch12_audit_log_detects_tampering_and_stores_no_payload():
    payload = _run("ch12.tamper_evident_audit_log").returned
    assert payload["tamper_detected"] is True
    assert payload["payload_stored_in_log"] is False


# --- Chapter 13 and 14 ------------------------------------------------ #

def test_ch13_aggregate_quality_hides_the_cohort_gap():
    payload = _run("ch13.quality_parity_across_cohorts").returned
    per_cohort = payload["per_cohort"]
    assert payload["gap"] > 0.1
    assert min(per_cohort.values()) < payload["aggregate_groundedness"]
    assert max(per_cohort.values()) > payload["aggregate_groundedness"]


def test_ch14_review_outcomes_are_recorded_not_just_requested():
    """"A human is in the loop" needs the outcome, not only the referral."""
    result = _run("ch14.review_queue_routing")
    reviewed = [
        s for s in result.spans if dict(s.attributes).get(Aiobs.HUMAN_REVIEW_REQUIRED)
    ]
    assert reviewed
    for span in reviewed:
        assert Aiobs.HUMAN_REVIEW_OUTCOME in dict(span.attributes)


# --- Chapter 15 to 17 ------------------------------------------------- #

def test_ch15_agent_handoffs_stay_in_one_trace():
    from aiobs.testing import assert_same_trace

    result = _run("ch15.agent_handoff_trace")
    assert_same_trace(result.spans)
    assert result.returned["handoff_depth"] == 3  # planner, researcher, writer, critic


def test_ch16_retry_loop_is_caught_with_zero_http_errors():
    payload = _run("ch16.silent_retry_loop_detected").returned
    assert payload["http_errors"] == 0
    assert payload["uptime_pct"] > 99.9
    assert "FM-1.3" in payload["mast_failure_modes"]
    assert payload["over_budget"] is True


def test_ch16_failure_vector_names_modes_not_a_pass_rate():
    payload = _run("ch16.failure_vector_across_runs").returned
    assert payload["failure_vector"]
    assert all(k.startswith("FM-") for k in payload["failure_vector"])


def test_ch17_accountability_chain_reaches_a_human():
    payload = _run("ch17.accountability_chain").returned
    assert payload["originating_principal"] == "human_operator"
    assert payload["unbroken"] is True
    assert payload["chain"][0]["authorized_by"] == "human_operator"
