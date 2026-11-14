"""leadline-profile + the training profile cache: the plugin builds a profile and an initial rating (every field
sourced or marked inferred), revises them on request with a `changes` trail, and `ProfileStore` keeps each version.
`get_or_build` calls Venus only on a miss. All model calls here are FakeModel replies."""
import copy
import json

import pytest
from conftest import PLUGINS

from profiles import ProfileError, ProfileStore, case_runner, get_or_build, update_profile, update_problems
from venus import FakeModel, InputError, fake_text, load_plugin

USER = {"id": "c_subject", "kind": "startup", "name": "Northstar Storage", "website": "https://northstar.example",
        "fields": {"pitch": "Grid battery software", "country": "Finland"}}
CALA = [{"company": "Northstar Storage", "country": "Finland", "stage": "Seed", "sector": "Climate",
         "round_date": "Apr 2025", "investors": "Aurora Ventures (lead), Lake Angels"}]


def profile_output(country="Finland", stage="seed", sectors=("climate", "software"), changes=(), total=0.7,
                   sources=None):
    facts = [{"id": "f1", "kind": "dataset", "ref": "cala:northstar"},
             {"id": "f2", "kind": "web", "url": "https://northstar.example/about"}]
    profile = {"id": "c_subject", "kind": "startup", "name": "Northstar Storage", "website": "https://northstar.example",
               "country": country, "stage": stage, "sectors": list(sectors), "facts": facts,
               "sources": sources if sources is not None else {
                   "website": {"facts": ["f2"]}, "country": {"facts": ["f1"]}, "stage": {"facts": ["f1"]},
                   "sectors": {"inferred": True}}}
    profile = {k: v for k, v in profile.items() if v is not None}
    return {"profile": profile, "rating": {"total": total, "parts": {"fit": total}, "sources": ["f1"]},
            "changes": list(changes)}


def reply(output):
    return fake_text(json.dumps({"output": output, "sources": ["https://northstar.example/about"]}))


@pytest.fixture(scope="module")
def plugin():
    return load_plugin(PLUGINS / "leadline-profile")


# --- the plugin -------------------------------------------------------------------------------------------------

def test_loads_with_seed_tendencies(plugin):
    assert plugin.name == "leadline-profile" and len(plugin.seed_tendencies) >= 3 and plugin.web_enabled


def test_input_shapes(plugin):
    plugin.validate_input({"user": USER})
    plugin.validate_input({"user": USER, "cala_facts": CALA, "as_of": "2025-01-01"})
    current = profile_output()
    plugin.validate_input({"user": USER, "current": {"profile": current["profile"], "rating": current["rating"]},
                           "update": {"reason": "user edited sectors", "new_info": {"sectors": ["energy"]}}})
    for bad in ({"user": {k: v for k, v in USER.items() if k != "kind"}},
                {"user": USER, "update": {"reason": "x", "new_info": {}}},  # an update needs the current profile
                {"user": USER, "cala_facts": "rows"}):
        with pytest.raises(InputError):
            plugin.validate_input(bad)


def test_output_shape_and_match_compatibility(plugin):
    out = profile_output()
    plugin.validate_output(out)
    for bad in ({k: v for k, v in out.items() if k != "rating"},
                {**out, "profile": {k: v for k, v in out["profile"].items() if k != "sources"}},
                {**out, "rating": {**out["rating"], "total": 1.5}},
                {**out, "changes": [{"field": "stage", "old": "pre-seed", "new": "seed"}]}):  # no reason
        with pytest.raises(InputError):
            plugin.validate_output(bad)
    match = load_plugin(PLUGINS / "leadline-match")  # the profile feeds leadline-match as is
    investor = {"id": "i_lead", "kind": "investor", "name": "Aurora Ventures"}
    match.validate_input({"subject": {**out["profile"], "rating": out["rating"]}, "candidates": [investor],
                          "request": {"direction": "startup_to_investors", "top_k": 5, "as_of": "2025-01-01"}})


def test_checker_matches_known_facts_and_sources(plugin):
    inp = {"user": USER, "cala_facts": CALA}
    expected = profile_output()
    assert plugin.check(inp, profile_output(), expected).total == 1.0
    wrong = plugin.check(inp, profile_output(country="Sweden", sectors=("fintech",)), expected)
    assert wrong.parts["field_match"] < 1 and wrong.total < 1
    unsourced = plugin.check(inp, profile_output(sources={}), expected)
    assert unsourced.parts["sourced"] == 0.0
    ghost = plugin.check(inp, profile_output(sources={"country": {"facts": ["f9"]}}), expected)  # no such fact
    assert ghost.parts["sourced"] < 1


def test_first_build_must_not_list_changes(plugin):
    s = plugin.check({"user": USER}, profile_output(changes=[
        {"field": "stage", "old": None, "new": "seed", "reason": "new"}]), profile_output())
    assert s.total == 0.0 and s.reasons


# --- update rules -----------------------------------------------------------------------------------------------

def update_input(update_reason="user says they raised a seed+ round"):
    cur = profile_output(stage="pre-seed")
    return {"user": USER, "current": {"profile": cur["profile"], "rating": cur["rating"]},
            "update": {"reason": update_reason, "new_info": {"stage": "seed"}}}


def test_update_with_a_matching_change_is_clean():
    out = profile_output(changes=[{"field": "stage", "old": "pre-seed", "new": "seed", "reason": "user update"}])
    assert update_problems(update_input(), out) == []


def test_update_problems():
    inp = update_input()
    assert update_problems(inp, profile_output())  # stage changed, no change entry
    assert update_problems(inp, profile_output(changes=[
        {"field": "stage", "old": "series-a", "new": "seed", "reason": "x"}]))  # wrong old value
    dropped = profile_output(country=None, changes=[{"field": "stage", "old": "pre-seed", "new": "seed",
                                                     "reason": "user update"}])
    assert any("country" in p for p in update_problems(inp, dropped))  # sourced field dropped with no reason
    renamed = profile_output(changes=[{"field": "stage", "old": "pre-seed", "new": "seed", "reason": "x"}])
    renamed["profile"]["id"] = "c_other"
    assert any("id" in p for p in update_problems(inp, renamed))
    listed = profile_output(changes=[{"field": "stage", "old": "pre-seed", "new": "seed", "reason": "x"},
                                     {"field": "country", "old": "Finland", "new": "Finland", "reason": "x"}])
    assert any("country" in p for p in update_problems(inp, listed))  # listed but unchanged
    rated = profile_output(total=0.9, changes=[{"field": "stage", "old": "pre-seed", "new": "seed", "reason": "x"}])
    assert any("rating" in p for p in update_problems(inp, rated))  # rating moved with no entry
    reorder = copy.deepcopy(inp)
    reorder["current"]["profile"]["sectors"] = ["software", "climate"]
    assert update_problems(reorder, profile_output(changes=[
        {"field": "stage", "old": "pre-seed", "new": "seed", "reason": "x"}])) == []  # order of a list is no change


# --- the store and the cache ------------------------------------------------------------------------------------

def test_store_versions_and_reopen(tmp_path):
    db = tmp_path / "profiles.sqlite"
    store = ProfileStore(db)
    assert store.get("c_subject") is None
    v1 = store.put("c_subject", profile_output()["profile"], {"total": 0.7, "parts": {}, "sources": []}, [])
    v2 = store.put("c_subject", profile_output(stage="series-a")["profile"], {"total": 0.8, "parts": {}, "sources": []},
                   [{"field": "stage", "old": "seed", "new": "series-a", "reason": "x"}])
    assert (v1, v2) == (1, 2)
    again = ProfileStore(db)
    latest = again.get("c_subject")
    assert latest["version"] == 2 and latest["profile"]["stage"] == "series-a" and latest["created_at"]
    assert again.get("c_subject", version=1)["profile"]["stage"] == "seed"
    assert [r["version"] for r in again.history("c_subject")] == [1, 2]


def test_get_or_build_calls_venus_only_on_a_miss(tmp_path):
    model = FakeModel([reply(profile_output())])
    run = case_runner(model)
    store = ProfileStore(tmp_path / "p.sqlite")
    first = get_or_build(store, USER, run, cala_facts=CALA)
    assert first["version"] == 1 and len(model.calls) == 1 and run.calls == 1
    second = get_or_build(store, USER, run, cala_facts=CALA)
    assert second == first and len(model.calls) == 1 and run.calls == 1  # 0 Venus calls on a hit


def test_time_split_profiles_are_kept_apart(tmp_path):
    model = FakeModel([reply(profile_output()), reply(profile_output(stage="pre-seed"))])
    store = ProfileStore(tmp_path / "p.sqlite")
    run = case_runner(model)
    a = get_or_build(store, USER, run, as_of="2025-01-01")
    b = get_or_build(store, USER, run, as_of="2024-01-01")
    assert a["key"] != b["key"] and run.calls == 2
    assert model.calls[0]["messages"][-1]["content"].count("2025-01-01") >= 1  # as_of goes into the input


def test_update_writes_version_two_with_changes(tmp_path):
    store = ProfileStore(tmp_path / "p.sqlite")
    changed = profile_output(stage="series-a", total=0.8, changes=[
        {"field": "stage", "old": "seed", "new": "series-a", "reason": "user reports a series A"},
        {"field": "rating", "old": 0.7, "new": 0.8, "reason": "later stage, more traction"}])
    model = FakeModel([reply(profile_output()), reply(changed)])
    run = case_runner(model)
    first = get_or_build(store, USER, run)
    new = update_profile(store, first["key"], {"reason": "user edit", "new_info": {"stage": "series-a"}}, run)
    assert new["version"] == 2 and new["profile"]["stage"] == "series-a"
    assert new["changes"] == changed["changes"]
    sent = model.calls[1]["messages"][-1]["content"]
    assert '"current"' in sent and '"update"' in sent


def test_update_that_drops_a_sourced_field_without_reason_is_refused(tmp_path):
    store = ProfileStore(tmp_path / "p.sqlite")
    dropped = profile_output(country=None)
    dropped["profile"]["sources"].pop("country")
    model = FakeModel([reply(profile_output()), reply(dropped)])
    run = case_runner(model)
    first = get_or_build(store, USER, run)
    with pytest.raises(ProfileError, match="country"):
        update_profile(store, first["key"], {"reason": "refresh", "new_info": {}}, run)
    assert store.get(first["key"])["version"] == 1  # nothing written


def test_update_needs_a_stored_profile(tmp_path):
    with pytest.raises(ProfileError):
        update_profile(ProfileStore(tmp_path / "p.sqlite"), "nobody", {"reason": "x", "new_info": {}},
                       case_runner(FakeModel([])))


# --- review fixes -----------------------------------------------------------------------------------------------

def test_unsourced_fields_are_never_stored():
    first = {"user": USER}
    assert any("country" in p for p in update_problems(first, profile_output(
        sources={"website": {"facts": ["f2"]}, "stage": {"facts": ["f1"]}, "sectors": {"inferred": True}})))
    ghost = profile_output()
    ghost["profile"]["facts"] = [f for f in ghost["profile"]["facts"] if f["id"] != "f1"]  # country cites f1
    assert any("country" in p for p in update_problems(first, ghost))


def test_rating_parts_count_and_total_is_their_mean():
    inp = update_input()
    stage = {"field": "stage", "old": "pre-seed", "new": "seed", "reason": "x"}
    moved = profile_output(changes=[stage])
    moved["rating"]["parts"] = {"fit": 0.7, "team": 0.7}  # total stays 0.7, parts changed
    assert any("rating" in p for p in update_problems(inp, moved))
    off = profile_output(total=0.9, changes=[stage, {"field": "rating", "old": 0.7, "new": 0.9, "reason": "x"}])
    off["rating"]["parts"] = {"fit": 0.1}
    assert any("mean" in p for p in update_problems(inp, off))


def test_case_only_edits_and_empty_dicts_are_no_change():
    inp = update_input()
    stage = {"field": "stage", "old": "pre-seed", "new": "seed", "reason": "x"}
    assert update_problems(inp, profile_output(country="FINLAND", changes=[stage])) == []
    empty = profile_output(changes=[stage])
    empty["profile"]["check_size"] = {"min": None, "max": None, "currency": None}
    assert update_problems(inp, empty) == []


def test_extra_profile_keys_and_facts_without_ref_are_refused(plugin):
    extra = profile_output()
    extra["profile"]["lead_share_guess"] = 0.5
    bare = profile_output()
    bare["profile"]["facts"].append({"id": "f3", "kind": "web"})
    for bad in (extra, bare):
        with pytest.raises(InputError):
            plugin.validate_output(bad)


def test_description_wording_does_not_count_against_field_match(plugin):
    expected = profile_output()
    expected["profile"]["description"] = "Grid battery software."
    got = profile_output()
    got["profile"]["description"] = "Software for grid batteries."
    got["profile"]["sources"]["description"] = {"facts": ["f2"]}
    assert plugin.check({"user": USER}, got, expected).parts["field_match"] == 1.0


def test_stale_update_is_refused_and_a_concurrent_build_is_reused(tmp_path):
    store = ProfileStore(tmp_path / "p.sqlite")
    v1 = profile_output()
    store.put("k", v1["profile"], v1["rating"], [])
    with pytest.raises(ProfileError, match="version"):
        store.put("k", v1["profile"], v1["rating"], [], expected_version=0)
    assert store.put("k", v1["profile"], v1["rating"], [], expected_version=1) == 2

    class Racer:  # another writer stores the profile while this build runs
        calls = 0

        def __call__(self, value):
            store.put("c_subject", v1["profile"], v1["rating"], [])
            return profile_output()
    built = get_or_build(store, USER, Racer())
    assert built["version"] == 1 and len(store.history("c_subject")) == 1
