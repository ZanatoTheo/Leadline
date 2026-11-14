"""Phase 6: top-N selection from stored profiles, the rank job, and the refresh check. Offline: a stub match agent."""
import json
import sys
from datetime import date
from pathlib import Path

import pytest

import jobs
import ranking
from db import LeadlineDb
from runtime import AgentBridge

RATING = {"total": 0.5, "parts": {}, "sources": []}
STARTUP = {"id": "founder:f1", "kind": "startup", "name": "Carbonlens", "stage": "seed", "country": "Germany",
           "sectors": ["Climate Tech"], "raising": {"amount": 1_500_000, "currency": "EUR"}, "facts": [],
           "sources": {"stage": {"facts": []}}}


def investor(name, **fields):
    base = {"id": f"investor:{name}", "kind": "investor", "name": name, "stages": ["seed"], "regions": ["Europe"],
            "sectors": ["climate"], "check_size": {"min": 250_000, "max": 2_000_000, "currency": "EUR"}, "facts": []}
    return {**base, **fields}


def record(profile, total=0.5, version=1):
    return {"key": profile["id"], "version": version, "profile": profile,
            "rating": {"total": total, "parts": {"fit": total}, "sources": []}, "changes": []}


class StubMatchAgent:
    """settings() + run(): ranks the candidates it is given in input order; counts its runs."""

    def __init__(self, settings=None, error=None):
        self._settings, self.error, self.inputs = settings or {}, error, []

    def settings(self, plugin_id, strategy=None):
        return dict(self._settings)

    def run(self, plugin_id, input_data, strategy=None, *, trace_id=None, on_cala_result=None):
        self.inputs.append(input_data)
        head = {"plugin": plugin_id, "mode": "run", "strategy": "s", "trace_id": trace_id, "warnings": [],
                "usage": {"model_calls": 1}}
        if self.error:
            return {**head, "status": "error", "outputs": [], "error": {"code": self.error, "message": "down"}}
        matches = [{"candidate_id": c["id"], "rank": i + 1, "score": round(0.9 - i * 0.05, 2), "score_parts": {},
                    "role": "lead", "active": True, "confidence": "high", "reasons": [{"text": "fit", "evidence": []}]}
                   for i, c in enumerate(input_data["candidates"])]
        return {**head, "status": "ok", "base_model": {"provider": "verda", "model": "nemotron"},
                "outputs": [{"output": {"matches": matches, "rejected": [], "evidence": [], "warnings": [],
                                        "stats": {}}, "sources": [], "status": "ok"}]}


@pytest.fixture
def db(tmp_path):
    return LeadlineDb(tmp_path / "leadline.db")


# --- fit score ----------------------------------------------------------------------------------------------------

def test_a_full_fit_scores_one_and_parts_are_weighted():
    assert ranking.fit_score(STARTUP, investor("a")) == pytest.approx(1.0)
    assert ranking.fit_score(investor("a"), STARTUP) == pytest.approx(1.0)  # either side can be the subject
    assert sum(ranking.FIT_WEIGHTS.values()) == pytest.approx(1.0)
    assert 0 <= ranking.fit_score(STARTUP, investor("b", sectors=["fintech"], stages=["series-a"])) < 1


@pytest.mark.parametrize("field,mismatch", [
    ("sectors", ["fintech"]), ("stages", ["series-a"]), ("regions", ["France", "Spain"]),
    ("check_size", {"min": 1_600_000, "max": 5_000_000, "currency": "EUR"})])
def test_an_unknown_field_never_scores_below_a_known_mismatch(field, mismatch):
    known_bad = ranking.fit_score(STARTUP, investor("bad", **{field: mismatch}))
    unknown = ranking.fit_score(STARTUP, investor("unknown", **{field: None if field == "check_size" else []}))
    assert unknown > known_bad
    assert unknown < ranking.fit_score(STARTUP, investor("good"))


# --- top-N selection ----------------------------------------------------------------------------------------------

def test_select_top_n_keeps_the_best_n_by_fit_then_rating():
    good = [ranking.match_profile(record(investor(f"g{i}"), total=i / 100)) for i in range(15)]
    worse = [ranking.match_profile(record(investor(f"w{i}", stages=["series-a"]), total=0.99)) for i in range(10)]
    top = ranking.select_top_n(ranking.match_profile(record(STARTUP)), good + worse, {}, n=10)
    keys = [k for k, _ in top["selected"]]
    assert len(keys) == 10
    assert keys == [f"investor:g{i}" for i in range(14, 4, -1)]  # full fit first; ties by rating, highest first
    assert all(fit == pytest.approx(1.0) for _, fit in top["selected"])


def test_a_prefilter_clash_is_never_selected():
    clash = ranking.match_profile(record(investor("late", stages=["series-c"]), total=1.0))
    ok = ranking.match_profile(record(investor("ok", stages=["series-a"]), total=0.1))
    top = ranking.select_top_n(ranking.match_profile(record(STARTUP)), [clash, ok], {}, n=10)
    assert [k for k, _ in top["selected"]] == ["investor:ok"]
    assert top["rejected"] == [{"candidate_id": "investor:late", "reason": "stage_mismatch",
                                "detail": top["rejected"][0]["detail"]}]


def test_trained_settings_turn_a_rule_off():
    clash = ranking.match_profile(record(investor("late", stages=["series-c"])))
    top = ranking.select_top_n(ranking.match_profile(record(STARTUP)), [clash], {"rules": ["out_of_region"]}, n=10)
    assert [k for k, _ in top["selected"]] == ["investor:late"]


def test_match_profile_uses_the_key_as_id_and_carries_the_rating():
    p = ranking.match_profile({**record(STARTUP, total=0.7), "profile": {**STARTUP, "id": "something-else"}})
    assert p["id"] == "founder:f1" and p["rating"] == {"total": 0.7, "parts": {"fit": 0.7}}
    assert "sources" not in p


# --- AgentBridge.rank ---------------------------------------------------------------------------------------------

def test_rank_sends_exactly_n_selected_candidates_to_the_match_agent(db):
    agent = StubMatchAgent()
    pool = [record(investor(f"i{i:02d}"), total=i / 100) for i in range(25)]
    resp = AgentBridge(db, agent).rank(record(STARTUP), pool, top_k=10, trace_id="t1")
    assert resp["status"] == "ok" and len(agent.inputs) == 1
    sent = agent.inputs[0]
    assert len(sent["candidates"]) == 10
    assert sent["request"] == {"direction": "startup_to_investors", "top_k": 10, "as_of": date.today().isoformat()}
    assert sent["subject"]["id"] == "founder:f1"
    assert [k for k, _ in resp["selected"]] == [c["id"] for c in sent["candidates"]]
    assert resp["settings"] == {}


def test_rank_with_every_candidate_filtered_makes_no_model_call(db):
    agent = StubMatchAgent()
    resp = AgentBridge(db, agent).rank(record(STARTUP), [record(investor("late", stages=["series-c"]))])
    assert agent.inputs == [] and resp["status"] == "ok" and resp["selected"] == []
    assert resp["outputs"][0]["output"]["matches"] == []
    assert resp["prefilter_rejected"][0]["candidate_id"] == "investor:late"


# --- rank job -----------------------------------------------------------------------------------------------------

def put(db, profile, total=0.5):
    return db.put(profile["id"], profile, {**RATING, "total": total}, [])


def founder_user(db, fid, discoverable=True, **profile):
    rec = db.upsert_founder({"id": fid, "profile": {"startupName": fid}, "founderName": "A", "email": f"{fid}@x.y",
                             "discoverable": discoverable})
    p = {**STARTUP, "id": f"founder:{rec['id']}", "name": fid, **profile}
    put(db, p)
    return f"founder:{rec['id']}"


def rank_job(db, key):
    return db.enqueue_job("rank", key) and {**db.claim_job(), "trace_id": "trace-1"}


def test_rank_job_stores_the_ranking_of_the_selected_candidates(db):
    put(db, STARTUP)
    for i in range(12):
        put(db, investor(f"i{i:02d}"), total=i / 100)
    agent = StubMatchAgent()

    result = jobs.run_rank_job(db, agent, rank_job(db, "founder:f1"))

    stored = db.latest_ranking("founder:f1")
    assert result["trace_id"] == "trace-1" and stored["trace_id"] == "trace-1"
    assert stored["subject_version"] == 1
    assert len(stored["candidates"]) == 10 and stored["candidates"][0] == {"key": "investor:i11", "version": 1}
    assert [m["candidate_id"] for m in stored["payload"]["matches"]][:2] == ["investor:i11", "investor:i10"]
    assert [k for k, _ in stored["payload"]["selected"]] == [c["key"] for c in stored["candidates"]]
    assert stored["payload"]["settings"] == {}
    assert len(agent.inputs) == 1


def test_rank_job_with_no_candidates_stores_an_empty_ranking_without_a_model_call(db):
    put(db, STARTUP)
    agent = StubMatchAgent()
    jobs.run_rank_job(db, agent, rank_job(db, "founder:f1"))
    stored = db.latest_ranking("founder:f1")
    assert agent.inputs == [] and stored["candidates"] == [] and stored["payload"]["matches"] == []


def test_an_investor_is_ranked_against_discoverable_founders_only(db):
    put(db, investor("fjord"))
    shown = founder_user(db, "f-shown")
    founder_user(db, "f-hidden", discoverable=False)
    agent = StubMatchAgent()
    jobs.run_rank_job(db, agent, rank_job(db, "investor:fjord"))
    sent = agent.inputs[0]
    assert sent["request"]["direction"] == "investor_to_startups"
    assert [c["id"] for c in sent["candidates"]] == [shown]


def test_a_match_agent_error_fails_the_rank_job_and_keeps_the_old_ranking(db):
    put(db, STARTUP)
    put(db, investor("a"))
    with pytest.raises(jobs.JobFailed, match="model_unavailable: down"):
        jobs.run_rank_job(db, StubMatchAgent(error="model_unavailable"), rank_job(db, "founder:f1"))
    assert db.latest_ranking("founder:f1") is None


def test_rank_job_without_a_stored_profile_fails(db):
    with pytest.raises(jobs.JobFailed, match="no stored profile"):
        jobs.run_rank_job(db, StubMatchAgent(), rank_job(db, "founder:nobody"))


# --- refresh check ------------------------------------------------------------------------------------------------

def ranked(db, n_investors=10, settings=None):
    put(db, STARTUP)
    for i in range(n_investors):
        put(db, investor(f"i{i:02d}"), total=0.5)
    jobs.run_rank_job(db, StubMatchAgent(settings), rank_job(db, "founder:f1"))
    db.finish_job(db.job_state("rank", "founder:f1")["id"])


def test_needs_rerank_is_false_right_after_ranking(db):
    ranked(db)
    assert ranking.needs_rerank(db, "founder:f1") is False


def test_needs_rerank_when_a_better_fitting_profile_joins(db):
    ranked(db)
    put(db, investor("weak", stages=["series-a"]), total=0.9)  # fits, but less than the 10 stored
    assert ranking.needs_rerank(db, "founder:f1") is False  # does not make the top 10
    put(db, investor("strong"), total=0.9)
    assert ranking.needs_rerank(db, "founder:f1") is True


def test_needs_rerank_when_the_subject_or_a_selected_candidate_changed(db):
    ranked(db)
    put(db, investor("i03", sectors=["climate", "energy"]))  # a new version of a selected candidate
    assert ranking.needs_rerank(db, "founder:f1") is True
    ranked_again = db.latest_ranking("founder:f1")
    assert ranked_again is not None
    db2_key = "founder:f1"
    jobs.run_rank_job(db, StubMatchAgent(), rank_job(db, db2_key))
    db.finish_job(db.job_state("rank", db2_key)["id"])
    assert ranking.needs_rerank(db, db2_key) is False
    put(db, {**STARTUP, "stage": "pre-seed"})  # the subject's own profile changed
    assert ranking.needs_rerank(db, db2_key) is True


def test_needs_rerank_with_no_ranking_yet_or_no_profile(db):
    assert ranking.needs_rerank(db, "founder:f1") is False  # nothing to rank: the profile job comes first
    put(db, STARTUP)
    assert ranking.needs_rerank(db, "founder:f1") is True


def test_needs_rerank_uses_the_settings_the_ranking_was_made_with(db):
    put(db, STARTUP)
    put(db, investor("late", stages=["series-c"]))
    jobs.run_rank_job(db, StubMatchAgent({"rules": ["out_of_region"]}), rank_job(db, "founder:f1"))
    assert [c["key"] for c in db.latest_ranking("founder:f1")["candidates"]] == ["investor:late"]
    assert ranking.needs_rerank(db, "founder:f1") is False  # same rules as the stored ranking: no flip-flop


# --- the real exported agent (offline: FakeModel) -----------------------------------------------------------------

INJECTED = Path(__file__).resolve().parents[1] / "agent"


def _agent_modules():
    return {m for m in sys.modules if m == "leadline_agent" or m.startswith("leadline_agent.")}


@pytest.fixture
def clean_agent_import():
    saved_path, saved = list(sys.path), {m: sys.modules.pop(m) for m in _agent_modules()}
    yield
    for m in _agent_modules():
        del sys.modules[m]
    sys.modules.update(saved)
    sys.path[:] = saved_path


@pytest.mark.skipif(not (INJECTED / "leadline_agent" / "__init__.py").is_file(),
                    reason="no injected agent at leadline/agent (run scripts/inject_agent.sh)")
def test_rank_job_input_passes_the_injected_match_agent(db, clean_agent_import):
    sys.path.insert(0, str(INJECTED))
    from leadline_agent.fake import FakeModel, fake_text

    put(db, {**STARTUP, "facts": [{"id": "d-1", "kind": "dataset", "ref": "r1"}]})
    put(db, investor("fjord", facts=[{"id": "d-2", "kind": "dataset", "ref": "r2"}]))
    out = {"matches": [{"candidate_id": "investor:fjord", "candidate_type": "investor", "rank": 1, "score": 0.8,
                        "score_parts": {"fit": 0.8}, "role": "lead", "active": {"status": "active"},
                        "confidence": "medium",
                        "reasons": [{"text": "climate seed fund in Europe", "evidence": ["e1"]}]}],
           "rejected": [], "evidence": [{"id": "e1", "kind": "dataset", "ref": "r2"}], "warnings": []}
    answer = fake_text(json.dumps({"output": out, "sources": []}))
    _, match = jobs.make_agents({}, agent_root=INJECTED, model=FakeModel([answer] * 3))

    jobs.run_rank_job(db, match, rank_job(db, "founder:f1"))

    stored = db.latest_ranking("founder:f1")
    assert [m["candidate_id"] for m in stored["payload"]["matches"]] == ["investor:fjord"]


# --- review fixes -------------------------------------------------------------------------------------------------

def test_a_stage_list_with_a_name_we_cannot_place_counts_as_unknown():
    late = {**STARTUP, "stage": "series-c"}
    partly = ranking.fit_parts(late, investor("a", stages=["Pre-seed", "Angel"]))["stage"]
    assert partly == ranking.UNKNOWN == ranking.fit_parts(late, investor("b", stages=["Angel"]))["stage"]
    assert ranking.fit_parts(STARTUP, investor("c", stages=["seed", "Angel"]))["stage"] == 1.0  # a stated match


def test_needs_rerank_waits_for_a_pending_rank_job_and_stops_after_a_failed_one(db):
    put(db, STARTUP)
    put(db, investor("a"))
    db.enqueue_job("rank", "founder:f1")
    assert ranking.needs_rerank(db, "founder:f1") is False  # one is already queued
    job = db.claim_job()
    assert ranking.needs_rerank(db, "founder:f1") is False  # and running
    db.finish_job(job["id"], error="model_unavailable: down")
    assert ranking.needs_rerank(db, "founder:f1") is False  # page loads don't retry a failing model
    jobs.run_rank_job(db, StubMatchAgent(), rank_job(db, "founder:f1"))
    db.finish_job(db.job_state("rank", "founder:f1")["id"])
    put(db, investor("b"), total=0.9)
    assert ranking.needs_rerank(db, "founder:f1") is True  # a ranking made after the failure: back to normal


def test_candidates_cut_for_size_are_not_stored_as_selected(db, monkeypatch):
    import runtime
    real = runtime._configured_prefilter

    def tight(settings):
        module = real(settings)
        module.MAX_INPUT_CHARS = 900  # subject alone 359 chars, with one slimmed candidate 708, with two 1059
        return module
    monkeypatch.setattr(runtime, "_configured_prefilter", tight)
    put(db, STARTUP)
    for i in range(4):
        put(db, investor(f"i{i}", description="x" * 600), total=i / 10)
    agent = StubMatchAgent()
    jobs.run_rank_job(db, agent, rank_job(db, "founder:f1"))
    sent = [c["id"] for c in agent.inputs[0]["candidates"]]
    stored = db.latest_ranking("founder:f1")
    assert 0 < len(sent) < 4
    assert [c["key"] for c in stored["candidates"]] == sent
    assert [k for k, _ in stored["payload"]["selected"]] == sent


def test_a_subject_too_large_for_the_input_fails_with_a_clear_code(db):
    put(db, {**STARTUP, "name": "N" * 30_000})
    put(db, investor("a"))
    with pytest.raises(jobs.JobFailed, match="input_too_large"):
        jobs.run_rank_job(db, StubMatchAgent(), rank_job(db, "founder:f1"))


def test_the_configured_prefilter_is_loaded_once_per_settings(monkeypatch):
    calls = []
    real = ranking._configured_prefilter
    monkeypatch.setattr(ranking, "_configured_prefilter", lambda s: calls.append(s) or real(s))
    monkeypatch.setattr(ranking, "_by_settings", {})
    subject = ranking.match_profile(record(STARTUP))
    for _ in range(3):
        ranking.select_top_n(subject, [ranking.match_profile(record(investor("a")))], {"rules": ["out_of_region"]})
    assert len(calls) == 1


def test_needs_rerank_stays_false_after_a_ranking_with_cut_candidates(db, monkeypatch):
    import runtime
    real = runtime._configured_prefilter

    def tight(settings):
        module = real(settings)
        module.MAX_INPUT_CHARS = 900
        return module
    monkeypatch.setattr(runtime, "_configured_prefilter", tight)
    put(db, STARTUP)
    for i in range(4):
        put(db, investor(f"i{i}", description="x" * 600), total=i / 10)
    jobs.run_rank_job(db, StubMatchAgent(), rank_job(db, "founder:f1"))
    db.finish_job(db.job_state("rank", "founder:f1")["id"])
    assert db.latest_ranking("founder:f1")["payload"]["unseen"]
    assert ranking.needs_rerank(db, "founder:f1") is False  # the cut ones were offered: no endless re-rank
