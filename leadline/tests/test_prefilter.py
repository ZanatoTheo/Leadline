"""prefilter.build_input: drop a candidate only on an observed clash (stage, region, check size, sector); unknown
keeps; the result is a valid leadline-match input under 25,000 characters; the true lead always survives."""
import copy
import importlib.util
import json

import pytest
from conftest import PLUGINS, company_profile, investor_profile

from venus import load_plugin

spec = importlib.util.spec_from_file_location("prefilter", PLUGINS / "leadline-match" / "prefilter.py")
prefilter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prefilter)
build_input = prefilter.build_input

REQUEST = {"direction": "startup_to_investors", "top_k": 5, "as_of": "2025-01-01"}


@pytest.fixture(scope="module")
def match_plugin():
    return load_plugin(PLUGINS / "leadline-match")


def startup(**kw):
    base = {"id": "s1", "kind": "startup", "name": "S", "country": "Finland", "stage": "seed",
            "sectors": ["climate", "software"], "raising": {"amount": 1_000_000, "currency": "EUR"}}
    return {**base, **kw}


def investor(cid="i1", **kw):
    base = {"id": cid, "kind": "investor", "name": cid.upper()}
    return {**base, **kw}


def kept_ids(result):
    return [c["id"] for c in (result["input"] or {}).get("candidates", [])]  # None: nothing left


def dropped(result):
    return {r["candidate_id"]: r["reason"] for r in result["rejected"]}


def test_fixture_true_lead_survives_and_input_is_valid(dataset, match_plugin):
    subject = company_profile(dataset["companies"][0])
    candidates = [investor_profile(i) for i in dataset["investors"]]
    result = build_input(subject, candidates, REQUEST)
    match_plugin.validate_input(result["input"])
    assert "i_lead" in kept_ids(result)  # the real lead of the held-out round


@pytest.mark.parametrize("cand,reason", [
    (investor(stages=["series-b", "series-c"]), "stage_mismatch"),
    (investor(regions=["United States"]), "out_of_region"),
    (investor(check_size={"min": 5_000_000, "max": 20_000_000, "currency": "EUR"}), "size_mismatch"),
    (investor(check_size={"min": 5_000, "max": 20_000, "currency": "EUR"}), "size_mismatch"),
    (investor(sectors=["fintech", "insurance"]), "sector_mismatch"),
])
def test_observed_clash_drops(cand, reason):
    result = build_input(startup(), [cand], REQUEST)
    assert dropped(result) == {"i1": reason} and kept_ids(result) == []
    assert result["rejected"][0]["detail"]


@pytest.mark.parametrize("cand", [
    investor(),  # nothing known
    investor(stages=[], regions=[], sectors=[], check_size=None),
    investor(stages=["Seed", "Series A"]),  # case and spaces
    investor(stages=["early stage"]),  # a word we can't place: keep
    investor(regions=["Nordics"]),  # Finland is in the Nordics
    investor(regions=["Europe"]),
    investor(regions=["global"]),
    investor(regions=["Atlantis"]),  # unknown region name: keep
    investor(country="United States"),  # HQ abroad is no reason to drop
    investor(check_size={"min": 5_000_000, "max": 20_000_000, "currency": "USD"}),  # other currency: can't compare
    investor(check_size={"min": None, "max": None, "currency": "EUR"}),
    investor(check_size={"min": 3_000_000, "max": 100_000, "currency": "EUR"}),  # min > max: bad data, ignore
    investor(sectors=["Climate Tech"]),  # loose sector match
    investor(sectors=["generalist"]),
])
def test_unknown_or_fitting_keeps(cand):
    result = build_input(startup(), [cand], REQUEST)
    assert kept_ids(result) == ["i1"], result["rejected"]


@pytest.mark.parametrize("subject_change", [
    {"stage": None}, {"country": None}, {"raising": None}, {"sectors": []},
])
def test_unknown_subject_fields_never_drop(subject_change):
    cands = [investor("a", stages=["series-b"]), investor("b", regions=["United States"]),
             investor("c", check_size={"min": 5_000_000, "max": 9_000_000, "currency": "EUR"}),
             investor("d", sectors=["fintech"])]
    keep_rule = {"stage": "a", "country": "b", "raising": "c", "sectors": "d"}[next(iter(subject_change))]
    result = build_input(startup(**subject_change), cands, REQUEST)
    assert keep_rule in kept_ids(result)


def test_investor_to_startups_uses_the_same_rules():
    subject = investor("i0", stages=["seed"], regions=["Nordics"], sectors=["climate"],
                       check_size={"min": 100_000, "max": 1_000_000, "currency": "EUR"})
    cands = [startup(id="ok"), startup(id="late", stage="series-c"), startup(id="far", country="Brazil"),
             startup(id="big", raising={"amount": 50_000_000, "currency": "EUR"}), startup(id="other", sectors=["games"])]
    result = build_input(subject, cands, {**REQUEST, "direction": "investor_to_startups"})
    assert kept_ids(result) == ["ok"]
    assert dropped(result) == {"late": "stage_mismatch", "far": "out_of_region", "big": "size_mismatch",
                               "other": "sector_mismatch"}


def test_duplicates_subject_and_wrong_kind_are_cut_not_rejected(match_plugin):
    cands = [investor("i1"), investor("i1", name="again"), startup(id="s1"), startup(id="s2")]
    result = build_input(startup(), cands, REQUEST)
    assert kept_ids(result) == ["i1"]
    assert sorted((c["candidate_id"], c["reason"]) for c in result["cut"]) == [
        ("i1", "duplicate"), ("s1", "subject"), ("s2", "wrong_kind")]
    assert result["rejected"] == []
    match_plugin.validate_input(result["input"])


def test_input_stays_under_the_size_cap(match_plugin):
    long = "x" * 5000
    cands = [investor(f"i{n}", description=long, facts=[{"id": f"f{n}-{k}", "kind": "web", "url": "https://a.example",
                                                         "quote": long} for k in range(20)])
             for n in range(60)]
    result = build_input(startup(description=long), cands, REQUEST)
    assert len(json.dumps(result["input"])) < prefilter.MAX_INPUT_CHARS == 25_000
    match_plugin.validate_input(result["input"])
    assert kept_ids(result)[0] == "i0"  # order kept; any cut comes off the end
    assert all(c["reason"] == "size_cap" for c in result["cut"])
    assert len(kept_ids(result)) + len(result["cut"]) == 60


def test_inputs_are_not_changed():
    subject, cands = startup(), [investor(stages=["series-b"])]
    before = copy.deepcopy((subject, cands))
    build_input(subject, cands, REQUEST)
    assert (subject, cands) == before


def test_nothing_left_is_reported_not_raised():
    result = build_input(startup(), [investor(stages=["series-c"])], REQUEST)
    assert result["input"] is None and result["rejected"]


# --- review fixes: a real lead must never be dropped by a vocabulary mismatch ----------------------------------

@pytest.mark.parametrize("subject_kw,cand", [
    ({"country": "USA"}, investor(regions=["United States"])),
    ({"country": "UK"}, investor(regions=["United Kingdom"])),
    ({"country": "United States"}, investor(regions=["US"])),
    ({"country": "Israel"}, investor(regions=["EMEA"])),
    ({"country": "Turkey"}, investor(regions=["Europe"])),
    ({"stage": "growth"}, investor(stages=["late"])),
    ({"stage": "Seed"}, investor(stages=["angel"])),
    ({"stage": "Seed"}, investor(stages=["pre-seed"])),
    ({"stage": "series-a"}, investor(stages=["seed"])),
    ({"sectors": ["Fintech"]}, investor(sectors=["Financial Technology"])),
    ({"sectors": ["HealthTech"]}, investor(sectors=["Healthcare"])),
    ({"sectors": ["AI / LLMs"]}, investor(sectors=["artificial intelligence"])),
    ({"sectors": ["CleanTech / Ocean cleanup"]}, investor(sectors=["climate"])),
    ({"raising": {"amount": 0, "currency": "EUR"}}, investor(check_size={"min": 50_000, "max": 90_000, "currency": "EUR"})),
    ({"raising": {"amount": 1_000_000, "currency": "€"}}, investor(check_size={"min": 5_000_000, "max": None, "currency": "EUR"})),
    ({"raising": {"amount": "1000000", "currency": "EUR"}}, investor(check_size={"min": "50000", "max": "x", "currency": "EUR"})),
])
def test_synonyms_and_odd_values_keep(subject_kw, cand):
    result = build_input(startup(**subject_kw), [cand], REQUEST)
    assert kept_ids(result) == ["i1"], result["rejected"]


def test_numeric_strings_still_compare():
    big = investor(check_size={"min": "5000000", "max": "9000000", "currency": "EUR"})
    assert dropped(build_input(startup(), [big], REQUEST)) == {"i1": "size_mismatch"}


def test_at_most_200_candidates_and_request_is_copied(match_plugin):
    request = dict(REQUEST)
    result = build_input(startup(), [investor(f"i{n}") for n in range(260)], request)
    assert len(result["input"]["candidates"]) == 200 and len(result["cut"]) == 60
    assert all(c["reason"] == "size_cap" for c in result["cut"])
    match_plugin.validate_input(result["input"])
    assert result["input"]["request"] is not request


def test_a_subject_too_big_to_fit_is_an_error():
    with pytest.raises(ValueError, match="subject"):
        build_input(startup(name="n" * 30_000), [investor()], REQUEST)


def test_every_fixture_lead_survives(dataset, match_plugin):
    by_id = {c["id"]: c for c in dataset["companies"]}
    investors = [investor_profile(i) for i in dataset["investors"]]
    rounds = [r for r in dataset["rounds"] if any(x["role"] == "lead" for x in r["investors"])]
    assert len(rounds) >= 2
    for r in rounds:
        subject = company_profile(by_id[r["company_id"]])
        subject["raising"] = {"amount": r["amount"]["value"], "currency": r["amount"]["currency"]}
        result = build_input(subject, investors, {**REQUEST, "as_of": r["date"]})
        match_plugin.validate_input(result["input"])
        for x in r["investors"]:
            if x["role"] == "lead":
                assert x["investor_id"] in kept_ids(result), (r["id"], result["rejected"])
