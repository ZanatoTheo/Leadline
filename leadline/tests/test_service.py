"""Phase 7: the local HTTP service the frontend's server code calls. Every body is checked against the frontend's
types (contracts/schemas/), and no endpoint may touch the network or a model."""
import json
import socket
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import jsonschema
import pytest
from fastapi.testclient import TestClient

import jobs
import service
from db import LeadlineDb, deal_from_row
from test_ranking import STARTUP, StubMatchAgent, investor

SCHEMAS = Path(__file__).resolve().parents[2] / "contracts" / "schemas"
PERSONA = {"startupName": "Carbonlens", "oneLiner": "Measures and cuts Scope 3 emissions for mid-size manufacturers",
           "sector": "climate", "stage": "seed", "location": "Berlin, Germany", "region": "europe", "raiseEurM": 1.5,
           "competitors": ["Tracely"], "customers": "mid-size manufacturers"}
RATING = {"total": 0.5, "parts": {"fit": 0.5}, "sources": []}


def check(type_name, value):
    jsonschema.Draft7Validator(json.loads((SCHEMAS / f"{type_name}.json").read_text())).validate(value)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("an endpoint tried to use the network")
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


@pytest.fixture
def db(tmp_path):
    return LeadlineDb(tmp_path / "leadline.db")


@pytest.fixture
def client(db):
    return TestClient(service.create_app(db))


def new_user(client, role="founder", email="a@b.c", name="Alex"):
    r = client.post("/users", json={"role": role, "name": name, "email": email, "passwordHash": "salt:hash"})
    assert r.status_code == 200, r.text
    return r.json()


def founder_put(client, user_id, **over):
    body = {"profile": PERSONA, "founderName": "Alex", "email": "a@b.c", "discoverable": True, **over}
    return client.put(f"/users/{user_id}/founder", json=body)


# --- accounts -----------------------------------------------------------------------------------------------------

def test_users_create_read_and_duplicate_email(client):
    user = new_user(client, email=" A@B.c ")
    check("User", user)
    assert user["email"] == "a@b.c" and user["passwordHash"] == "salt:hash"
    dup = client.post("/users", json={"role": "investor", "name": "X", "email": "a@b.c", "passwordHash": ""})
    assert dup.status_code == 409 and dup.json()["error"]
    assert client.get("/users/by-email", params={"email": "A@b.c"}).json() == user
    assert client.get(f"/users/{user['id']}").json() == user
    assert client.get("/users/by-email", params={"email": "no@b.c"}).status_code == 404
    missing = client.get("/users/nope")
    assert missing.status_code == 404 and "error" in missing.json()


def test_bad_bodies_are_400_with_an_error(client):
    r = client.post("/users", json={"role": "admin", "name": "X", "email": "x@y.z", "passwordHash": ""})
    assert r.status_code == 400 and r.json()["error"]
    r = client.post("/users", content=b"not json", headers={"content-type": "application/json"})
    assert r.status_code == 400 and r.json()["error"]
    assert client.get("/no-such-route").json() == {"error": "Not Found"}


def test_sessions_round_trip_and_expiry(client):
    user = new_user(client)
    later = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    assert client.post("/sessions", json={"userId": user["id"], "token": "t1", "expiresAt": later}).status_code == 204
    got = client.get("/sessions/t1").json()
    check("User", got["user"])
    assert got["user"]["id"] == user["id"] and got["profile"] is None and got["discoverable"] is True
    founder_put(client, user["id"], discoverable=False)
    got = client.get("/sessions/t1").json()
    check("FounderProfile", got["profile"])
    assert got["discoverable"] is False and got["user"]["founderId"]
    assert client.delete("/sessions/t1").status_code == 204
    assert client.get("/sessions/t1").status_code == 404
    earlier = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    client.post("/sessions", json={"userId": user["id"], "token": "old", "expiresAt": earlier})
    assert client.get("/sessions/old").status_code == 404
    assert client.post("/sessions", json={"userId": "nobody", "token": "t2", "expiresAt": later}).status_code == 404


# --- founders, funds, demo users ----------------------------------------------------------------------------------

def test_founder_upsert_queues_one_profile_job_and_a_second_upsert_none(client, db):
    user = new_user(client)
    r = founder_put(client, user["id"])
    assert r.status_code == 200, r.text
    record = r.json()
    check("FounderRecord", record)
    key = f"founder:{record['id']}"
    assert db.job_state("profile", key)["status"] == "queued"
    again = founder_put(client, user["id"], profile={**PERSONA, "oneLiner": "Changed"}).json()
    assert again["id"] == record["id"] and again["profile"]["oneLiner"] == "Changed"
    assert db.jobs_summary()["queued"] == 1  # editing is out of scope: no second build
    assert client.get(f"/founders/{record['id']}").json() == again
    listed = client.get("/founders", params={"discoverable": "1"}).json()
    assert [f["id"] for f in listed] == [record["id"]]
    for f in listed:
        check("FounderRecord", f)
    assert client.get("/founders/nope").status_code == 404


def test_founder_upsert_checks_the_profile_and_the_role(client):
    user = new_user(client)
    bad = founder_put(client, user["id"], profile={**PERSONA, "sector": "space"})
    assert bad.status_code == 400 and "profile" in bad.json()["error"]
    inv = new_user(client, role="investor", email="i@b.c")
    assert founder_put(client, inv["id"]).status_code == 403
    assert founder_put(client, "nobody").status_code == 404


def test_investor_fund_sets_the_name_and_queues_the_investor_profile_once(client, db):
    inv = new_user(client, role="investor", email="i@b.c", name="Sam")
    r = client.put(f"/users/{inv['id']}/investor-fund", json={"investorName": "Fjord Ventures"})
    assert r.status_code == 204
    assert client.get(f"/users/{inv['id']}").json()["investorName"] == "Fjord Ventures"
    assert db.job_state("profile", "investor:fjord-ventures")["status"] == "queued"
    client.put(f"/users/{inv['id']}/investor-fund", json={"investorName": "Fjord Ventures"})
    assert db.jobs_summary()["queued"] == 1
    founder = new_user(client)
    assert client.put(f"/users/{founder['id']}/investor-fund", json={"investorName": "X"}).status_code == 403


def test_demo_users_are_made_once_with_their_founder_record(client, db):
    body = {"role": "founder", "email": "demo-founder@leadline.local", "name": "Alex", "persona": PERSONA}
    first = client.post("/demo-users", json=body).json()
    check("User", first)
    second = client.post("/demo-users", json=body).json()
    assert first["id"] == second["id"] and first["founderId"] == second["founderId"]
    assert db.user_by_id(first["id"])["isDemo"] is True
    assert db.founder(first["founderId"])["profile"] == PERSONA
    inv = client.post("/demo-users", json={"role": "investor", "email": "demo-investor@leadline.local", "name": "Sam",
                                           "investorName": "Fjord Ventures"}).json()
    assert inv["investorName"] == "Fjord Ventures"
    assert db.jobs_summary()["queued"] == 2  # one profile job each
    assert client.post("/demo-users", json={"role": "founder", "email": "d2@x.y", "name": "N"}).status_code == 400


# --- intros -------------------------------------------------------------------------------------------------------

def test_intros_create_list_and_answer(client):
    founder = new_user(client)
    record = founder_put(client, founder["id"]).json()
    inv = new_user(client, role="investor", email="i@b.c", name="Sam")
    client.put(f"/users/{inv['id']}/investor-fund", json={"investorName": "Fjord Ventures"})
    body = {"founderId": record["id"], "investor": "Fjord Ventures", "direction": "founder-to-investor", "note": "Hi"}
    intro = client.post("/intros", json=body).json()
    check("Intro", intro)
    assert client.post("/intros", json=body).json()["id"] == intro["id"]  # a pending duplicate is returned
    assert [i["id"] for i in client.get("/intros", params={"founderId": record["id"]}).json()] == [intro["id"]]
    assert [i["id"] for i in client.get("/intros", params={"investor": "fjord ventures"}).json()] == [intro["id"]]
    assert client.patch(f"/intros/{intro['id']}", json={"userId": founder["id"], "status": "accepted"}).status_code == 403
    done = client.patch(f"/intros/{intro['id']}", json={"userId": inv["id"], "status": "passed",
                                                        "passReason": "Too early"})
    assert done.status_code == 200
    check("Intro", done.json())
    assert done.json()["status"] == "passed" and done.json()["passReason"] == "Too early"
    again = client.patch(f"/intros/{intro['id']}", json={"userId": inv["id"], "status": "accepted"})
    assert again.status_code == 409
    assert client.patch("/intros/nope", json={"userId": inv["id"], "status": "accepted"}).status_code == 404
    bad = client.patch(f"/intros/{intro['id']}", json={"userId": inv["id"], "status": "maybe"})
    assert bad.status_code == 400


# --- market data --------------------------------------------------------------------------------------------------

def _days_ago(n):
    return (date.today() - timedelta(days=n)).isoformat()


ROWS = [
    {"company": "Mistral AI", "country": "France", "sector": "AI / LLMs", "stage": "seed", "round_date": _days_ago(30),
     "investors": "Lightspeed Venture Partners (lead)", "company_description": "Open large language models"},
    {"company": "Fractile", "country": "UK", "sector": "AI chips", "stage": "Series A", "round_date": _days_ago(400),
     "investors": "Kindred (lead), Oxford Science", "company_description": "Chips for running language models"},
    {"company": "Shopware", "country": "Germany", "sector": "Retail software", "stage": "seed",
     "round_date": _days_ago(10), "investors": "Fjord Ventures (lead)", "company_description": "Online shops"},
    {"company": "Ocean Co", "country": "Europe", "sector": "CleanTech / Ocean cleanup", "stage": "seed",
     "round_date": _days_ago(20), "investors": "Fjord Ventures (lead)", "company_description": "Cleans the ocean"},
    {"company": "Wise Pay", "country": "Sweden", "sector": "Fintech / Remittances", "stage": "seed",
     "round_date": _days_ago(5), "investors": "Nordic Angels", "company_description": "Cheap remittances"},
]


@pytest.fixture
def market(db):
    for row in ROWS:
        db.upsert_round(deal_from_row(row), "cala")
    db.upsert_fund_close({"investor": "Fjord Ventures", "fundName": "Fjord Climate Fund II", "sizeEurM": 120,
                          "closed": _days_ago(15), "sources": []}, "cala")
    db.upsert_fund_close({"investor": "Kindred", "fundName": "Kindred IV", "sizeEurM": 300,
                          "closed": _days_ago(500), "sources": []}, "cala")
    db.upsert_entity({"id": "e1", "name": "Fjord Ventures", "entity_type": "Organization"}, "cala")
    return db


def companies(resp):
    assert resp.status_code == 200, resp.text
    for d in resp.json():
        check("Deal", d)
    return [d["company"] for d in resp.json()]


def test_deals_filter_by_sector_stage_region_and_age(client, market):
    assert companies(client.get("/deals", params={"sector": "ai"})) == ["Mistral AI", "Fractile"]  # not "Retail"
    assert companies(client.get("/deals", params={"sector": "climate"})) == ["Ocean Co"]
    assert companies(client.get("/deals", params={"sector": "fintech", "region": "nordics"})) == ["Wise Pay"]
    assert companies(client.get("/deals", params={"region": "uk"})) == ["Fractile"]
    assert set(companies(client.get("/deals", params={"region": "europe"}))) == {r["company"] for r in ROWS}
    assert companies(client.get("/deals", params={"region": "dach"})) == ["Shopware"]
    assert companies(client.get("/deals", params={"stage": "series-a"})) == ["Fractile"]
    assert "Fractile" not in companies(client.get("/deals", params={"sinceDays": "365"}))
    assert client.get("/deals", params={"sector": "space"}).status_code == 400
    assert client.get("/deals", params={"sinceDays": "soon"}).status_code == 400


def test_deals_by_investor_company_and_similar(client, market):
    assert companies(client.get("/deals/investor", params={"name": "fjord ventures"})) == ["Shopware", "Ocean Co"]
    assert companies(client.get("/deals/investor", params={"name": "Fjord Ventures", "sinceDays": "15"})) == \
        ["Shopware"]
    assert companies(client.get("/deals/company", params={"name": "fractile"})) == ["Fractile"]
    similar = companies(client.get("/deals/similar", params={"description": "Small language models for chips",
                                                             "sector": "ai"}))
    assert similar == ["Fractile", "Mistral AI"]  # 3 shared words (language, models, chips), then 2; Retail none
    assert client.get("/deals/company").status_code == 400


def test_funds_and_fund_closes(client, market):
    funds = client.get("/funds", params={"investor": "Fjord Ventures"}).json()
    for f in funds:
        check("FundClose", f)
    assert [f["fundName"] for f in funds] == ["Fjord Climate Fund II"]
    recent = client.get("/fund-closes", params={"sector": "climate", "sinceDays": "90"}).json()
    assert [f["fundName"] for f in recent] == ["Fjord Climate Fund II"]
    assert client.get("/fund-closes", params={"sector": "ai", "sinceDays": "90"}).json() == []
    assert [f["fundName"] for f in client.get("/fund-closes", params={"sinceDays": "1000"}).json()] == \
        ["Fjord Climate Fund II", "Kindred IV"]


def test_entities_and_status(client, market, db):
    hits = client.get("/entities", params={"name": "fjord", "limit": "5"}).json()
    for h in hits:
        check("CalaEntity", h)
    assert hits[0] == {"id": "e1", "name": "Fjord Ventures", "entity_type": "Organization"}
    db.enqueue_job("profile", "founder:x")
    assert client.get("/status").json() == {"mode": "live", "jobs": {"queued": 1, "running": 0, "failed": 0}}


def test_status_is_simulated_without_cala_rows(client):
    assert client.get("/status").json()["mode"] == "simulated"


# --- token auth and health (deploy mode) ---------------------------------------------------------------------------

def test_healthz_is_always_open(db):
    app = service.create_app(db, token="s3cret")
    assert TestClient(app).get("/healthz").json() == {"ok": True}


def test_token_guards_everything_but_healthz(db):
    client = TestClient(service.create_app(db, token="s3cret"))
    for headers in ({}, {"authorization": "Bearer wrong"}, {"authorization": "s3cret"}):
        assert client.get("/status", headers=headers).status_code == 401, headers
        assert client.get("/healthz", headers=headers).status_code == 200, headers
    assert client.get("/status", headers={"authorization": "Bearer s3cret"}).status_code == 200


def test_no_token_means_no_auth(client):
    assert client.get("/status").status_code == 200


# --- agent results ------------------------------------------------------------------------------------------------

def test_profile_status_none_building_ready_failed(client, db):
    assert client.get("/profiles/founder:f1").json() == {"status": "none"}
    job = db.enqueue_job("profile", "founder:f1")
    assert client.get("/profiles/founder:f1").json() == {"status": "building"}
    db.claim_job()
    db.finish_job(job["id"], error="model_unavailable: down")
    assert client.get("/profiles/founder:f1").json() == {"status": "failed", "error": "model_unavailable: down"}
    db.put("founder:f1", STARTUP, RATING, [])
    got = client.get("/profiles/founder:f1").json()
    assert got["status"] == "ready" and got["profile"]["name"] == "Carbonlens" and got["version"] == 1
    assert got["rating"]["total"] == 0.5 and got["updatedAt"]
    assert client.get("/profiles/robot:1").status_code == 400


def _rank_now(db, key="founder:f1"):
    job = db.enqueue_job("rank", key)
    claimed = db.claim_job()
    assert claimed["id"] == job["id"]
    jobs.run_rank_job(db, StubMatchAgent(), {**claimed, "trace_id": "t"})
    db.finish_job(job["id"])


def test_ranking_read_queues_one_rank_job_and_never_runs_the_model(client, db):
    assert client.get("/rankings/founder:f1").json() == {"status": "none", "ranking": None}
    db.put("founder:f1", STARTUP, RATING, [])
    db.put("investor:a", investor("a"), RATING, [])
    first = client.get("/rankings/founder:f1").json()
    second = client.get("/rankings/founder:f1").json()
    assert first == second == {"status": "building", "ranking": None}
    assert db.jobs_summary()["queued"] == 1 and db.job_state("rank", "founder:f1")["status"] == "queued"


def test_ranking_read_returns_the_stored_ranking_and_new_candidates(client, db):
    db.put("founder:f1", STARTUP, RATING, [])
    for i in range(3):
        db.put(f"investor:i{i}", {**investor(f"i{i}"), "name": f"Fund {i}"}, {**RATING, "total": i / 10}, [])
    _rank_now(db)
    got = client.get("/rankings/founder:f1").json()
    assert got["status"] == "ready" and db.jobs_summary()["queued"] == 0
    ranking = got["ranking"]
    assert [m["key"] for m in ranking["matches"]] == ["investor:i2", "investor:i1", "investor:i0"]
    first = ranking["matches"][0]
    assert first["name"] == "Fund 2" and first["kind"] == "investor" and first["rank"] == 1
    assert set(first) == {"key", "name", "kind", "score", "scoreParts", "confidence", "reasons", "rank"}
    assert ranking["newCandidates"] == [] and ranking["computedAt"]

    db.put("investor:new", {**investor("new"), "name": "New Fund"}, {**RATING, "total": 0.9}, [])
    got = client.get("/rankings/founder:f1").json()
    client.get("/rankings/founder:f1")
    assert got["status"] == "building" and db.jobs_summary()["queued"] == 1
    assert got["ranking"]["newCandidates"] == [{"key": "investor:new", "name": "New Fund", "fit": 1.0}]
    assert [m["key"] for m in got["ranking"]["matches"]][0] == "investor:i2"  # the old ranking still shows


def test_ranking_after_a_failed_rank_job(client, db):
    db.put("founder:f1", STARTUP, RATING, [])
    db.put("investor:a", investor("a"), RATING, [])
    job = db.enqueue_job("rank", "founder:f1")
    db.claim_job()
    db.finish_job(job["id"], error="model_unavailable: down")
    got = client.get("/rankings/founder:f1").json()
    assert got == {"status": "failed", "ranking": None, "error": "model_unavailable: down"}
    assert db.jobs_summary()["queued"] == 0


def _founder_with_profile(client, db):
    """A founder user whose first profile job has finished and whose profile is stored."""
    user = new_user(client)
    record = founder_put(client, user["id"]).json()
    key = f"founder:{record['id']}"
    job = db.claim_job()
    assert job["kind"] == "profile" and job["subject_key"] == key
    db.put(key, STARTUP, RATING, [])
    db.finish_job(job["id"])
    db.put("investor:a", investor("a"), RATING, [])
    return user, key


def test_saving_again_after_a_failed_rank_queues_one_rank_job(client, db):
    user, key = _founder_with_profile(client, db)
    rank = db.enqueue_job("rank", key)
    db.claim_job()
    db.finish_job(rank["id"], error="model_bad_reply: cut off")
    assert founder_put(client, user["id"]).status_code == 200
    assert db.job_state("rank", key)["status"] == "queued"
    assert db.job_state("profile", key)["status"] == "done"  # the stored profile is not rebuilt
    founder_put(client, user["id"])
    assert db.jobs_summary()["queued"] == 1  # a second save while it waits adds nothing


def test_saving_again_after_a_ready_ranking_queues_nothing(client, db):
    user, key = _founder_with_profile(client, db)
    _rank_now(db, key)
    assert founder_put(client, user["id"]).status_code == 200
    assert db.jobs_summary()["queued"] == 0


# --- serve.py -----------------------------------------------------------------------------------------------------

import sys  # noqa: E402

import serve  # noqa: E402

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


def test_env_file_never_overrides_and_reports_names_only(tmp_path):
    f = tmp_path / ".env"
    f.write_text("# keys\nexport A_KEY='secret-a'\nB_KEY=\"secret-b\"\nnot a line\nC_KEY=c\n")
    env = {"C_KEY": "kept"}
    assert serve.load_env_file(f, env) == ["A_KEY", "B_KEY"]
    assert env == {"A_KEY": "secret-a", "B_KEY": "secret-b", "C_KEY": "kept"}


def test_no_worker_build_serves_reads(tmp_path):
    app, worker = serve.build(tmp_path / "x.db", worker=False)
    assert worker is None and TestClient(app).get("/status").json()["mode"] == "simulated"


def test_build_passes_the_service_token_from_environ(tmp_path):
    app, _ = serve.build(tmp_path / "x.db", worker=False, environ={"LEADLINE_SERVICE_TOKEN": "s3cret"})
    client = TestClient(app)
    assert client.get("/status").status_code == 401
    assert client.get("/status", headers={"authorization": "Bearer s3cret"}).status_code == 200


@pytest.mark.skipif(not (INJECTED / "leadline_agent" / "__init__.py").is_file(),
                    reason="no injected agent at leadline/agent (run scripts/inject_agent.sh)")
def test_fake_model_build_runs_a_signup_to_ranking_offline(tmp_path, clean_agent_import):
    env = {"CONTEXT_DEV_API_KEY": "would-spend", "LEADLINE_LIVE_CALA": "1", "CALA_API_KEY": "would-spend"}
    app, worker = serve.build(tmp_path / "x.db", fake_model=True, environ=env, agent_root=INJECTED)
    client, db = TestClient(app), app.state.db
    db.put("investor:fjord", investor("fjord"), RATING, [])
    user = new_user(client)
    record = founder_put(client, user["id"]).json()
    key = f"founder:{record['id']}"
    profile_job = worker.run_once()
    assert profile_job["status"] == "done", profile_job
    assert client.get(f"/profiles/{key}").json()["profile"]["sectors"] == ["climate"]
    rank_job = worker.run_once()
    assert rank_job["kind"] == "rank" and rank_job["status"] == "done", rank_job
    got = client.get(f"/rankings/{key}").json()
    assert got["status"] == "ready" and [m["key"] for m in got["ranking"]["matches"]] == ["investor:fjord"]


# --- phase 7 review fixes -----------------------------------------------------------------------------------------

def test_a_founder_who_opts_out_leaves_an_investors_ranking_at_once(client, db):
    user = new_user(client)
    record = founder_put(client, user["id"]).json()
    fkey = f"founder:{record['id']}"
    db.put(fkey, {**STARTUP, "id": fkey}, RATING, [])
    db.put("investor:fjord", investor("fjord"), RATING, [])
    db.finish_job(db.claim_job()["id"])  # the founder's queued profile job, out of the way
    _rank_now(db, "investor:fjord")
    assert [m["key"] for m in client.get("/rankings/investor:fjord").json()["ranking"]["matches"]] == [fkey]
    founder_put(client, user["id"], discoverable=False)
    got = client.get("/rankings/investor:fjord").json()
    assert got["ranking"]["matches"] == []


def test_a_failed_first_build_is_queued_again_when_the_founder_saves(client, db):
    user = new_user(client)
    record = founder_put(client, user["id"]).json()
    key = f"founder:{record['id']}"
    job = db.claim_job()
    db.finish_job(job["id"], error="model_unavailable: down")
    assert client.get(f"/profiles/{key}").json()["status"] == "failed"
    founder_put(client, user["id"])
    assert client.get(f"/profiles/{key}").json()["status"] == "building"


def test_a_duplicate_session_token_is_409(client):
    user = new_user(client)
    later = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    client.post("/sessions", json={"userId": user["id"], "token": "t1", "expiresAt": later})
    dup = client.post("/sessions", json={"userId": user["id"], "token": "t1", "expiresAt": later})
    assert dup.status_code == 409 and dup.json()["error"]
    bad = client.post("/sessions", json={"userId": user["id"], "token": "t2", "expiresAt": "soon"})
    assert bad.status_code == 400


def test_a_huge_since_days_is_400(client):
    assert client.get("/deals", params={"sinceDays": "800000"}).status_code == 400
