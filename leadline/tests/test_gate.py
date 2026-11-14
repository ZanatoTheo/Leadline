"""leadline-match gate: rerun the prefilter with a strategy's knobs on time-split cases; filter recall must stay
>= 0.95, and a setting that drops a true lead is rejected with the case id. No model calls."""
import pytest
from conftest import PLUGINS
from test_build_cases import ROWS

from build_cases import build_cases
from venus import load_plugin
from venus.gate import gate
from venus.strategy import Strategy


@pytest.fixture(scope="module")
def plugin():
    return load_plugin(PLUGINS / "leadline-match")


def strategy(settings=None):
    return Strategy.from_dict({"id": "s", "plugin": "leadline-match", "plugin_version": "0.1.0", "status": "draft",
                               "base_model": {"model": "claude-fast"}, "tendencies": [],
                               "created_at": "2026-11-14T00:00:00Z", "settings": settings or {}})


def sized_case():
    """A lead whose largest check is 20% of the round: kept at the default share (5%), dropped at 50%."""
    subject = {"id": "s1", "kind": "startup", "name": "S", "country": "Finland", "stage": "seed",
               "sectors": ["climate"], "raising": {"amount": 1_000_000, "currency": "EUR"}}
    lead = {"id": "i_lead", "kind": "investor", "name": "Lead",
            "check_size": {"min": 50_000, "max": 200_000, "currency": "EUR"}}
    other = {"id": "i_other", "kind": "investor", "name": "Other"}
    match = {"candidate_id": "i_lead", "candidate_type": "investor", "rank": 1, "score": 1.0, "score_parts": {},
             "role": "lead", "active": {"status": "active"}, "confidence": "high",
             "reasons": [{"text": "led it", "evidence": ["e1"]}]}
    return {"id": "sized-case",
            "input": {"subject": subject, "candidates": [other, lead],
                      "request": {"direction": "startup_to_investors", "top_k": 5, "as_of": "2025-01-01"}},
            "expected": {"matches": [match], "rejected": [], "evidence": [{"id": "e1", "kind": "dataset",
                                                                          "ref": "x"}], "warnings": []}}


@pytest.fixture(scope="module")
def cases():
    built, _ = build_cases(ROWS)
    return built + [sized_case()]


def test_plugin_has_a_gate(plugin):
    assert plugin.gate_hook is not None


def test_default_settings_keep_every_lead(plugin, cases):
    r = gate(plugin, strategy(), cases)
    assert r["passed"], r["reasons"]
    m = r["metrics"]["plugin"]
    assert m["filter_recall"] == 1.0 and m["dropped_leads"] == [] and m["cases"] == len(cases)
    assert m["input_chars_per_case_max"] < 25_000 and m["input_tokens_per_case_est"] > 0


def test_a_setting_that_drops_a_true_lead_is_rejected_with_the_case_id(plugin, cases):
    r = gate(plugin, strategy({"min_check_share": 0.5}), cases)
    assert r["passed"] is False
    assert any("sized-case" in x and "i_lead" in x for x in r["reasons"])
    assert r["metrics"]["plugin"]["dropped_leads"] == [{"case_id": "sized-case", "candidate_id": "i_lead",
                                                        "reason": "size_mismatch"}]


def test_a_candidate_cap_that_cuts_the_lead_is_rejected(plugin, cases):
    r = gate(plugin, strategy({"max_candidates": 1}), [sized_case()])
    assert r["passed"] is False and any("sized-case" in x and "size_cap" in x for x in r["reasons"])


def test_turning_rules_off_keeps_recall(plugin, cases):
    assert gate(plugin, strategy({"rules": []}), cases)["passed"]
    assert gate(plugin, strategy({"rules": ["stage_mismatch", "out_of_region"]}), cases)["passed"]


def test_unknown_setting_is_rejected_by_the_core_gate(plugin, cases):
    r = gate(plugin, strategy({"min_share": 0.1}), cases)
    assert r["passed"] is False and any("min_share" in x for x in r["reasons"])


def test_recall_threshold_tolerates_one_loss_in_many(plugin):
    many = [dict(sized_case(), id=f"ok-{n}") for n in range(30)]
    lost = dict(sized_case(), id="lost")
    lost["input"] = {**lost["input"], "candidates": [{**c, "check_size": {"min": 5_000_000, "max": None,
                                                                          "currency": "EUR"}}
                                                     if c["id"] == "i_lead" else c
                                                     for c in lost["input"]["candidates"]]}
    r = gate(plugin, strategy(), many + [lost])  # 30/31 = 0.968 >= 0.95
    assert r["passed"] and r["metrics"]["plugin"]["filter_recall"] == pytest.approx(30 / 31)
    assert r["metrics"]["plugin"]["dropped_leads"][0]["case_id"] == "lost"


# --- phase 7 review fixes ---------------------------------------------------------------------------------------

def test_cases_without_true_leads_fail(plugin):
    empty = sized_case()
    empty["expected"] = {**empty["expected"], "matches": []}
    r = gate(plugin, strategy({"max_candidates": 1, "rules": []}), [empty])
    assert r["passed"] is False and any("true lead" in x for x in r["reasons"])


def test_any_lead_lost_only_because_of_the_settings_is_rejected_even_above_the_threshold(plugin):
    many = [dict(sized_case(), id=f"ok-{n}") for n in range(30)]
    r = gate(plugin, strategy({"min_check_share": 0.5}), many)
    assert r["passed"] is False and any("ok-0" in x for x in r["reasons"])  # 0/30 kept; every case is named
    one = [dict(sized_case(), id=f"keep-{n}", input={**sized_case()["input"], "subject": {
        **sized_case()["input"]["subject"], "raising": None}}) for n in range(30)] + [dict(sized_case(), id="only")]
    r = gate(plugin, strategy({"min_check_share": 0.5}), one)  # recall 30/31 >= 0.95, but "only" is a new loss
    assert r["passed"] is False and any("only" in x and "i_lead" in x for x in r["reasons"])


def test_subject_too_large_is_a_named_loss(plugin):
    big = sized_case()
    big["input"] = {**big["input"], "subject": {**big["input"]["subject"], "name": "n" * 30_000}}
    r = gate(plugin, strategy({"max_candidates": 5}), [big])
    assert r["passed"] is False and r["metrics"]["plugin"]["dropped_leads"][0]["reason"] == "subject_too_large"


def test_the_shared_prefilter_is_left_unchanged(plugin):
    import importlib.util
    spec = importlib.util.spec_from_file_location("pf_check", PLUGINS / "leadline-match" / "prefilter.py")
    before = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(before)
    gate(plugin, strategy({"rules": [], "min_check_share": 0.4, "max_candidates": 3}), [sized_case()])
    assert len(before.RULES) == 4 and before.MIN_CHECK_SHARE == 0.05 and before.MAX_CANDIDATES == 200
    from build_cases import prefilter as shared
    assert len(shared.RULES) == 4 and shared.MIN_CHECK_SHARE == 0.05 and shared.MAX_CANDIDATES == 200
