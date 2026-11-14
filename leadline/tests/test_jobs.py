"""leadline/jobs.py: the background worker and the profile job (phase 5). Offline: stub agents and FakeModel."""
import json
import sqlite3
import sys
import threading
import time
from pathlib import Path

import pytest

import jobs
from db import LeadlineDb

PERSONA = {"startupName": "Carbonlens", "oneLiner": "Measures and cuts Scope 3 emissions", "sector": "climate",
           "stage": "seed", "location": "Berlin, Germany", "region": "europe", "raiseEurM": 1.5,
           "competitors": ["Tracely"], "customers": "mid-size manufacturers"}
INJECTED = Path(__file__).resolve().parents[1] / "agent"


def profile_answer(key, name, kind="startup"):
    return {"profile": {"id": key, "kind": kind, "name": name, "sectors": ["climate"],
                        "facts": [{"id": "w-1", "kind": "web", "url": "https://example.com"}],
                        "sources": {"sectors": {"facts": ["w-1"]}}},
            "rating": {"total": 0.6, "parts": {"fit": 0.6}, "sources": ["w-1"]}, "changes": []}


class StubAgent:
    """Section 4.2 Agent: settings() + run(); answers with `answer(input)` or fails with `error_code`."""

    def __init__(self, answer=None, error_code=None, **init_kwargs):
        self.answer, self.error_code, self.init_kwargs = answer, error_code, init_kwargs
        self.inputs = []

    def settings(self, plugin_id, strategy=None):
        return {}

    def run(self, plugin_id, input_data, strategy=None, *, trace_id=None, on_cala_result=None):
        self.inputs.append((plugin_id, input_data))
        head = {"plugin": plugin_id, "mode": "run", "strategy": f"{plugin_id}-default", "trace_id": trace_id,
                "usage": {"model_calls": 2, "input_tokens": 10, "output_tokens": 5, "web_calls": 1, "cache_hits": 0,
                          "seconds": 0.1}, "warnings": []}
        if self.error_code:
            return {**head, "status": "error", "outputs": [],
                    "error": {"code": self.error_code, "message": "endpoint down"}}
        out = self.answer(input_data)
        return {**head, "status": "ok", "base_model": {"provider": "verda", "model": "nemotron-3.5-super-vl"},
                "outputs": [{"output": out, "sources": [], "status": "ok"}]}


@pytest.fixture
def db(tmp_path):
    return LeadlineDb(tmp_path / "leadline.db")


def founder(db):
    user = db.create_user("founder", "Alex", "a@b.c")
    record = db.upsert_founder({"profile": PERSONA, "founderName": "Alex", "email": "a@b.c", "discoverable": True})
    db.link_founder(user["id"], record["id"])
    return record


def ok_agent():
    return StubAgent(answer=lambda i: profile_answer(i["user"]["id"], i["user"]["name"], i["user"]["kind"]))


def worker(db, agent, **handlers):
    return jobs.Worker(db, {"profile": lambda d, job: jobs.run_profile_job(d, agent, job), **handlers})


def test_founder_profile_job_stores_version_1_and_queues_one_rank_job(db):
    record = founder(db)
    key = f"founder:{record['id']}"
    db.enqueue_job("profile", key)
    agent = ok_agent()

    job = worker(db, agent).run_once()

    assert job["status"] == "done" and job["kind"] == "profile"
    stored = db.get(key)
    assert stored["version"] == 1 and stored["profile"]["name"] == "Carbonlens"
    assert stored["rating"]["total"] == 0.6
    assert db.profile_status(key) == "ready"
    assert db.job_state("rank", key)["status"] == "queued"
    assert db.jobs_summary() == {"queued": 1, "running": 0, "done": 1, "failed": 0}
    plugin, payload = agent.inputs[0]
    assert plugin == "leadline-profile" and payload["user"]["id"] == key
    assert payload["user"]["fields"]["sector"] == "climate"
    assert db.job_state("profile", key)["trace_id"]  # the trace id the Cala hook stored replies under


def test_agent_error_fails_the_job_and_stores_nothing(db):
    key = f"founder:{founder(db)['id']}"
    db.enqueue_job("profile", key)

    job = worker(db, StubAgent(error_code="model_unavailable")).run_once()

    assert job["status"] == "failed" and job["error"].startswith("model_unavailable: endpoint down")
    assert db.get(key) is None and db.profile_status(key) == "failed"
    assert db.job_state("rank", key) is None  # no ranking without a profile


def test_investor_profile_job_sends_the_investors_rounds_as_cala_facts(db):
    user = db.create_user("investor", "Sam", "s@b.c")
    db.set_investor_name(user["id"], "Fjord Ventures")
    db.upsert_round({"company": "Carbonlens", "announced": "2025-03-15", "round": "seed", "amountEurM": 3.5,
                     "leadInvestors": ["Fjord Ventures"], "otherInvestors": [], "sources": []}, "cala")
    db.upsert_round({"company": "Other", "announced": "2025-04-01", "leadInvestors": ["Someone Else"],
                     "otherInvestors": [], "sources": []}, "cala")
    db.enqueue_job("profile", "investor:fjord-ventures")
    agent = ok_agent()

    assert worker(db, agent).run_once()["status"] == "done"

    _, payload = agent.inputs[0]
    assert payload["user"] == {"id": "investor:fjord-ventures", "kind": "investor", "name": "Fjord Ventures",
                               "website": None, "fields": {}}
    assert [r["company"] for r in payload["cala_facts"]] == ["Carbonlens"]
    assert payload["cala_facts"][0]["investors"] == "Fjord Ventures (lead)"
    assert db.get("investor:fjord-ventures")["profile"]["kind"] == "investor"


@pytest.mark.parametrize("key,msg", [("founder:missing", "no founder record"),
                                     ("investor:nobody", "no investor user"), ("robot:1", "unknown profile key")])
def test_profile_job_for_an_unknown_subject_fails_clearly(db, key, msg):
    db.enqueue_job("profile", key)
    job = worker(db, ok_agent()).run_once()
    assert job["status"] == "failed" and msg in job["error"]


def test_make_agents_keeps_cala_off_unless_live_cala_is_set(monkeypatch):
    built = []
    monkeypatch.setattr(jobs, "load_agent", lambda root=None, **kw: built.append(kw) or StubAgent(**kw))

    profile, match = jobs.make_agents({"CONTEXT_DEV_API_KEY": "k"})
    assert built[0]["cala"] is False and "web_tools" not in built[0]  # Context.dev tools come from the env
    assert built[1]["cala"] is False and built[1]["web_tools"] == []  # rank job: stored profiles only

    built.clear()
    jobs.make_agents({"LEADLINE_LIVE_CALA": "1"})
    assert built[0]["cala"] is True and built[1]["cala"] is False

    built.clear()
    sentinel = object()
    jobs.make_agents({}, model=sentinel)  # --fake-model: one injected model for both agents
    assert built[0]["model"] is sentinel and built[1]["model"] is sentinel


def test_an_unexpected_exception_fails_the_job_and_the_worker_goes_on(db):
    key = f"founder:{founder(db)['id']}"
    db.enqueue_job("profile", key)

    def boom(d, job):
        raise RuntimeError("a bug")
    w = jobs.Worker(db, {"profile": boom})
    job = w.run_once()
    assert job["status"] == "failed" and "RuntimeError: a bug" in job["error"]
    assert w.run_once() is None  # nothing left, no crash


def test_a_job_with_no_handler_fails(db):
    db.enqueue_job("rank", "founder:1")
    job = jobs.Worker(db, {}).run_once()
    assert job["status"] == "failed" and "no handler" in job["error"]


def test_recover_requeues_a_job_left_running_by_a_crash(db):
    key = f"founder:{founder(db)['id']}"
    db.enqueue_job("profile", key)
    db.claim_job()  # a worker took it and died
    con = sqlite3.connect(db.path)
    con.execute("UPDATE jobs SET started_at = '2000-01-01T00:00:00+00:00'")
    con.commit()
    con.close()

    w = worker(db, ok_agent())
    assert w.recover() == 1
    job = w.run_once()
    assert job["status"] == "done" and job["attempts"] == 2


def test_worker_thread_runs_queued_jobs_until_stopped(db):
    key = f"founder:{founder(db)['id']}"
    w = jobs.Worker(db, {"profile": lambda d, job: jobs.run_profile_job(d, ok_agent(), job),
                         "rank": lambda d, job: {"note": "ranked"}}, poll_s=0.05)
    w.start()
    try:
        db.enqueue_job("profile", key)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and db.jobs_summary()["done"] < 2:
            time.sleep(0.05)
    finally:
        w.stop()
    assert db.jobs_summary() == {"queued": 0, "running": 0, "done": 2, "failed": 0}  # profile, then its rank job
    assert not w.running


def _agent_modules():
    return {m for m in sys.modules if m == "leadline_agent" or m.startswith("leadline_agent.")}


@pytest.fixture
def clean_agent_import():
    """load_agent() puts the agent root on sys.path and leaves leadline_agent imported; undo both afterwards so
    later tests that load an agent from another root don't get this one."""
    saved_path = list(sys.path)
    saved = {m: sys.modules.pop(m) for m in _agent_modules()}
    yield
    for m in _agent_modules():
        del sys.modules[m]
    sys.modules.update(saved)
    sys.path[:] = saved_path


@pytest.mark.skipif(not (INJECTED / "leadline_agent" / "__init__.py").is_file(),
                    reason="no injected agent at leadline/agent (run scripts/inject_agent.sh)")
def test_profile_job_with_the_injected_agent_and_a_fake_model(db, clean_agent_import):
    sys.path.insert(0, str(INJECTED))
    from leadline_agent.fake import FakeModel, fake_text

    record = founder(db)
    key = f"founder:{record['id']}"
    answer = json.dumps({"output": profile_answer(key, "Carbonlens"), "sources": ["https://example.com"]})
    profile_agent, match_agent = jobs.make_agents({}, agent_root=INJECTED, model=FakeModel([fake_text(answer)]))
    assert type(profile_agent).__module__.startswith("leadline_agent")

    db.enqueue_job("profile", key)
    job = jobs.Worker(db, {"profile": lambda d, j: jobs.run_profile_job(d, profile_agent, j)}).run_once()

    assert job["status"] == "done", job
    assert db.get(key)["profile"]["sectors"] == ["climate"]


# --- review fixes -------------------------------------------------------------------------------------------------

def test_a_profile_finished_while_its_rank_job_runs_queues_another_rank(db):
    key = f"founder:{founder(db)['id']}"
    db.enqueue_job("rank", key)
    db.claim_job()  # the rank job runs on the old profile
    db.enqueue_job("profile", key)

    worker(db, ok_agent()).run_once()

    queued = [j for j in (db.job_state("rank", key),) if j and j["status"] == "queued"]
    assert queued, "a rank job must wait to run on the new profile"
    assert db.jobs_summary()["running"] == 1  # the old rank job is untouched


def test_finish_is_retried_when_the_database_is_briefly_locked(db, monkeypatch):
    key = f"founder:{founder(db)['id']}"
    db.enqueue_job("profile", key)
    real, calls = db.finish_job, []

    def flaky(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise sqlite3.OperationalError("database is locked")
        return real(*args, **kwargs)
    monkeypatch.setattr(db, "finish_job", flaky)
    monkeypatch.setattr(jobs, "FINISH_RETRY_S", 0)

    assert worker(db, ok_agent()).run_once()["status"] == "done"
    assert len(calls) == 2


def test_start_requeues_jobs_a_stopped_process_left_running_at_once(db):
    key = f"founder:{founder(db)['id']}"
    db.enqueue_job("profile", key)
    db.claim_job()  # the previous process died mid-job a moment ago
    w = worker(db, ok_agent())
    w.poll_s = 0.05
    w.start()
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and db.profile_status(key) != "ready":
            time.sleep(0.05)
    finally:
        w.stop()
    assert db.profile_status(key) == "ready"


def test_start_after_a_stop_that_timed_out_keeps_the_worker_alive(db):
    gate = threading.Event()
    w = jobs.Worker(db, {"rank": lambda d, job: gate.wait(5) and {}}, poll_s=0.05)
    db.enqueue_job("rank", "founder:1")
    w.start()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and db.jobs_summary()["running"] == 0:
        time.sleep(0.02)
    w.stop(timeout=0.05)  # the job is still running: the thread outlives stop()
    w.start()
    gate.set()
    db.enqueue_job("rank", "founder:2")
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and db.jobs_summary()["done"] < 2:
        time.sleep(0.05)
    w.stop()
    assert db.jobs_summary()["done"] == 2


def test_a_crash_keeps_the_trace_id_of_the_run(db):
    key = f"founder:{founder(db)['id']}"
    db.enqueue_job("profile", key)
    seen = []

    def crash(d, job):
        seen.append(job["trace_id"])
        raise RuntimeError("after the Cala calls")
    job = jobs.Worker(db, {"profile": crash}).run_once()
    assert job["status"] == "failed" and seen[0] and job["trace_id"] == seen[0]


# --- phase 6: the rank handler --------------------------------------------------------------------------------------

def test_handlers_run_the_profile_job_then_the_rank_job(db):
    key = f"founder:{founder(db)['id']}"
    db.put("investor:fjord", {"id": "investor:fjord", "kind": "investor", "name": "Fjord", "sectors": ["climate"],
                              "facts": []}, {"total": 0.5, "parts": {}, "sources": []}, [])

    class Match:
        inputs = []

        def settings(self, plugin_id, strategy=None):
            return {}

        def run(self, plugin_id, input_data, strategy=None, *, trace_id=None, on_cala_result=None):
            self.inputs.append(input_data)
            out = {"matches": [{"candidate_id": "investor:fjord", "rank": 1, "score": 0.8, "score_parts": {},
                                "role": "lead", "active": True, "confidence": "high", "reasons": []}],
                   "rejected": [], "evidence": [], "warnings": []}
            return {"status": "ok", "trace_id": trace_id, "usage": {}, "warnings": [],
                    "outputs": [{"output": out, "sources": [], "status": "ok"}]}

    match = Match()
    db.enqueue_job("profile", key)
    w = jobs.Worker(db, jobs.handlers(ok_agent(), match))
    assert w.run_once()["kind"] == "profile"
    assert w.run_once()["status"] == "done"
    assert db.latest_ranking(key)["payload"]["matches"][0]["candidate_id"] == "investor:fjord"
    assert len(match.inputs) == 1 and w.run_once() is None
