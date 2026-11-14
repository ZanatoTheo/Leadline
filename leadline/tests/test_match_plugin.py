"""leadline-match: the plugin loads in Venus, its input/output schemas accept the real shapes and refuse bad ones,
and the checker scores a ranking against the true leads (top_hit, recall_at_k, unknown_penalty, total in [0, 1])."""
import copy
import json

import pytest
from conftest import PLUGINS, REPO

from venus import InputError, load_plugin

PLUGIN_DIR = PLUGINS / "leadline-match"


@pytest.fixture(scope="module")
def plugin():
    return load_plugin(PLUGIN_DIR)


def match(cid, rank, kind="investor"):
    return {"candidate_id": cid, "candidate_type": kind, "rank": rank, "score": round(1 - rank / 10, 2),
            "score_parts": {"fit": 0.8}, "role": "lead", "active": {"status": "active", "last_lead_date": None},
            "confidence": "medium", "reasons": [{"text": "led seed rounds in climate", "evidence": [f"d-{cid}"]}]}


def output(*ids, rejected=()):
    return {"matches": [match(cid, n) for n, cid in enumerate(ids, 1)],
            "rejected": [{"candidate_id": cid, "reason": "follower_only", "detail": "never led"} for cid in rejected],
            "evidence": [{"id": f"d-{cid}", "kind": "dataset", "ref": f"investor:{cid}"} for cid in (*ids, *rejected)],
            "warnings": []}


EXPECTED = output("i_lead")  # the true lead of the held-out round, in output form (Venus validates `expected` so)


def test_loads_with_seed_tendencies(plugin):
    assert plugin.name == "leadline-match"
    assert len(plugin.seed_tendencies) >= 4
    assert plugin.web_enabled


def test_fixture_input_and_contract_example_are_valid(plugin, match_input):
    plugin.validate_input(match_input)
    example = json.loads((REPO / "app/contracts/venus_request.example.json").read_text())
    assert example["plugin"] == "leadline-match"
    plugin.validate_input(example["input"])


@pytest.mark.parametrize("change", [
    lambda i: i.pop("candidates"),
    lambda i: i.__setitem__("candidates", []),
    lambda i: i["request"].pop("as_of"),
    lambda i: i["request"].__setitem__("top_k", 0),
    lambda i: i["request"].__setitem__("direction", "both"),
    lambda i: i["subject"].__setitem__("kind", "person"),
    lambda i: i["candidates"][0].pop("id"),
    lambda i: i["candidates"][0].__setitem__("lead_share", 1.5),
])
def test_bad_input_is_refused(plugin, match_input, change):
    bad = copy.deepcopy(match_input)
    change(bad)
    with pytest.raises(InputError):
        plugin.validate_input(bad)


def test_output_and_expected_shapes(plugin):
    plugin.validate_output(output("i_lead", "i_prior", rejected=["i_follower"]))
    plugin.validate_output(EXPECTED)
    for bad in (
        {k: v for k, v in EXPECTED.items() if k != "matches"},
        {**EXPECTED, "matches": [{**match("i_lead", 1), "candidate_type": "person"}]},
        {**EXPECTED, "matches": [{**match("i_lead", 1), "score": 2}]},
        {**EXPECTED, "rejected": [{"candidate_id": "i_x", "reason": "too_small", "detail": ""}]},
    ):
        with pytest.raises(InputError):
            plugin.validate_output(bad)


def test_perfect_ranking_scores_one(plugin, match_input):
    s = plugin.check(match_input, output("i_lead", "i_prior", rejected=["i_follower"]), EXPECTED)
    assert s.parts == {"top_hit": 1.0, "recall_at_k": 1.0, "unknown_penalty": 0.0}
    assert s.total == 1.0


def test_true_lead_second_gets_recall_but_no_top_hit(plugin, match_input):
    s = plugin.check(match_input, output("i_prior", "i_lead"), EXPECTED)
    assert s.parts["top_hit"] == 0.0 and s.parts["recall_at_k"] == 1.0
    assert 0 < s.total < 1


def test_true_lead_past_top_k_counts_as_missed(plugin, match_input):
    s = plugin.check(match_input, output("i_prior", "i_follower", "i_lead"), EXPECTED)  # top_k is 2
    assert s.parts["recall_at_k"] == 0.0 and s.total == 0.0
    assert any("i_lead" in r for r in s.reasons)


def test_rank_order_not_list_order_decides(plugin, match_input):
    out = output("i_prior", "i_lead")
    out["matches"][0]["rank"], out["matches"][1]["rank"] = 2, 1  # i_lead is rank 1 though listed second
    assert plugin.check(match_input, out, EXPECTED).parts["top_hit"] == 1.0


def test_invented_candidate_is_penalised(plugin, match_input):
    clean = plugin.check(match_input, output("i_lead", "i_prior"), EXPECTED)
    invented = plugin.check(match_input, output("i_lead", "i_ghost"), EXPECTED)
    assert invented.parts["unknown_penalty"] > 0
    assert invented.total < clean.total
    assert any("i_ghost" in r for r in invented.reasons)


def test_duplicates_and_the_subject_count_as_unknown(plugin, match_input):
    s = plugin.check(match_input, output("i_lead", "i_lead", "c_subject"), EXPECTED)
    assert s.parts["unknown_penalty"] > 0


def test_empty_answer_scores_zero(plugin, match_input):
    s = plugin.check(match_input, output(), EXPECTED)
    assert s.total == 0.0 and s.parts["recall_at_k"] == 0.0


def test_total_stays_in_range(plugin, match_input):
    ids = ["i_lead", "i_prior", "i_follower", "i_ghost", "c_subject"]
    for n in range(len(ids) + 1):
        for out in (output(*ids[:n]), output(*reversed(ids[:n])), output(*ids[:n], rejected=ids[n:])):
            assert 0.0 <= plugin.check(match_input, out, EXPECTED).total <= 1.0


def test_padding_rejected_does_not_hide_an_invented_match(plugin, match_input):
    inp = copy.deepcopy(match_input)
    inp["candidates"] += [{"id": f"i_pad{n}", "kind": "investor", "name": f"Pad {n}"} for n in range(50)]
    out = output("i_ghost", "i_lead", rejected=[f"i_pad{n}" for n in range(50)])
    assert plugin.check(inp, out, EXPECTED).parts["unknown_penalty"] >= 0.5


def test_duplicate_true_leads_count_once(plugin, match_input):
    expected = output("i_lead", "i_prior")
    expected["matches"].append(match("i_lead", 3))
    s = plugin.check(match_input, output("i_lead"), expected)
    assert s.parts["recall_at_k"] == 0.5


def test_no_known_lead_rewards_an_empty_ranking_only(plugin, match_input):
    none = output()
    assert plugin.check(match_input, output(rejected=["i_follower"]), none).total == 1.0
    assert plugin.check(match_input, output("i_prior"), none).total == 0.0


def test_match_type_must_fit_the_candidate_kind(plugin, match_input):
    out = output("i_lead", "i_prior")
    out["matches"][1]["candidate_type"] = "company"
    assert plugin.check(match_input, out, EXPECTED).parts["unknown_penalty"] > 0


@pytest.mark.parametrize("change", [
    lambda i: i["candidates"][0].__setitem__("kind", "startup"),  # startup_to_investors wants investors
    lambda i: i["subject"].__setitem__("kind", "investor"),
    lambda i: i["request"].__setitem__("as_of", "2025-13-45"),
])
def test_kinds_follow_the_direction_and_dates_are_real(plugin, match_input, change):
    bad = copy.deepcopy(match_input)
    change(bad)
    with pytest.raises(InputError):
        plugin.validate_input(bad)


def test_investor_to_startups_is_accepted(plugin, match_input):
    flipped = {"subject": {**match_input["candidates"][0]}, "candidates": [match_input["subject"]],
               "request": {**match_input["request"], "direction": "investor_to_startups"}}
    plugin.validate_input(flipped)


def test_every_reason_cites_evidence(plugin):
    bad = output("i_lead")
    bad["matches"][0]["reasons"][0]["evidence"] = []
    with pytest.raises(InputError):
        plugin.validate_output(bad)


def test_both_plugins_opt_in_to_runtime_cala_tools():
    from venus import load_plugin
    for name in ("leadline-match", "leadline-profile"):
        assert load_plugin(PLUGINS / name).cala_enabled is True
