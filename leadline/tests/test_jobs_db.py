"""leadline/db.py schema v2: background jobs, stored rankings, profile status, lookups the service needs, and the
additive migration from v1 files."""
import shutil
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from db import SCHEMA_VERSION, DbError, LeadlineDb, deal_from_row

REAL_DB = Path(__file__).resolve().parents[1] / "data" / "leadline.db"


@pytest.fixture
def db(tmp_path):
    return LeadlineDb(tmp_path / "leadline.db")


def _profile(name, kind="startup"):
    return {"id": name, "kind": kind, "name": name, "facts": [], "sources": {}}


# --- jobs ---------------------------------------------------------------------------------------------------------

def test_enqueue_dedups_queued_and_running_jobs(db):
    a = db.enqueue_job("profile", "founder:1")
    assert a["status"] == "queued" and a["attempts"] == 0
    assert db.enqueue_job("profile", "founder:1")["id"] == a["id"]
    assert db.enqueue_job("rank", "founder:1")["id"] != a["id"]  # other kind: its own job
    claimed = db.claim_job()
    assert claimed["id"] == a["id"] and claimed["status"] == "running" and claimed["attempts"] == 1
    again = db.enqueue_job("profile", "founder:1")  # running on old data: one more run is queued after it
    assert again["id"] != a["id"] and again["status"] == "queued"
    assert db.enqueue_job("profile", "founder:1")["id"] == again["id"]  # but only one waits


def test_enqueue_refuses_an_unknown_kind(db):
    with pytest.raises(DbError):
        db.enqueue_job("email", "founder:1")


def test_claim_takes_oldest_first_and_returns_none_when_empty(db):
    first = db.enqueue_job("profile", "founder:1")
    db.enqueue_job("profile", "founder:2")
    assert db.claim_job()["id"] == first["id"]
    assert db.claim_job()["subject_key"] == "founder:2"
    assert db.claim_job() is None


def test_two_threads_never_claim_the_same_job(db):
    ids = {db.enqueue_job("profile", f"founder:{i}")["id"] for i in range(30)}
    claimed, lock = [], threading.Lock()

    def worker():
        while (job := db.claim_job()) is not None:
            with lock:
                claimed.append(job["id"])

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(claimed) == sorted(ids)  # every job once, none twice


def test_finish_records_done_or_failed(db):
    a, b = db.enqueue_job("profile", "founder:1"), db.enqueue_job("rank", "founder:1")
    db.claim_job(), db.claim_job()
    db.finish_job(a["id"])
    db.finish_job(b["id"], error="model_unavailable: down")
    assert db.job_state("profile", "founder:1")["status"] == "done"
    failed = db.job_state("rank", "founder:1")
    assert failed["status"] == "failed" and failed["error"] == "model_unavailable: down"
    assert failed["finished_at"]
    assert db.jobs_summary() == {"queued": 0, "running": 0, "done": 1, "failed": 1}


def _age_running_jobs(db, seconds):
    old = (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()
    con = sqlite3.connect(db.path)
    con.execute("UPDATE jobs SET started_at = ? WHERE status = 'running'", (old,))
    con.commit()
    con.close()


def test_requeue_stale_gives_a_crashed_job_one_more_try_then_fails_it(db):
    job = db.enqueue_job("profile", "founder:1")
    db.claim_job()
    assert db.requeue_stale(older_than_s=600) == 0  # just started: not stale
    _age_running_jobs(db, 3600)
    assert db.requeue_stale(older_than_s=600) == 1
    assert db.job_state("profile", "founder:1")["status"] == "queued"
    assert db.claim_job()["attempts"] == 2
    _age_running_jobs(db, 3600)
    db.requeue_stale(older_than_s=600)
    state = db.job_state("profile", "founder:1")
    assert state["id"] == job["id"] and state["status"] == "failed" and "2 attempts" in state["error"]


# --- profiles and rankings ----------------------------------------------------------------------------------------

def test_profile_status_transitions(db):
    key = "founder:1"
    assert db.profile_status(key) == "none"
    job = db.enqueue_job("profile", key)
    assert db.profile_status(key) == "building"
    db.claim_job()
    assert db.profile_status(key) == "building"
    db.finish_job(job["id"], error="model_unavailable: down")
    assert db.profile_status(key) == "failed"
    db.put(key, _profile("A"), {"total": 0.5, "parts": {}, "sources": []}, [])
    assert db.profile_status(key) == "ready"  # a stored profile wins over an old failure


def test_latest_profiles_by_kind_newest_version_only(db):
    rating = {"total": 0.5, "parts": {}, "sources": []}
    db.put("founder:1", _profile("A"), rating, [])
    db.put("founder:1", _profile("A2"), rating, [])
    db.put("founder:2", _profile("B"), rating, [])
    db.put("investor:fjord", _profile("Fjord", "investor"), rating, [])
    db.put("carbonlens@2025-01-01", _profile("training"), rating, [])  # training keys are not users
    startups = db.latest_profiles("startup")
    assert {(p["key"], p["version"], p["profile"]["name"]) for p in startups} == {("founder:1", 2, "A2"),
                                                                                  ("founder:2", 1, "B")}
    assert [p["key"] for p in db.latest_profiles("investor")] == ["investor:fjord"]
    with pytest.raises(DbError):
        db.latest_profiles("robot")


def test_rankings_round_trip_newest_first(db):
    assert db.latest_ranking("founder:1") is None
    db.put_ranking("founder:1", 1, [{"key": "investor:a", "version": 1}], {"matches": [], "selected": []}, "t1")
    rid = db.put_ranking("founder:1", 2, [{"key": "investor:b", "version": 3}],
                         {"matches": [{"key": "investor:b"}], "selected": [["investor:b", 0.9]]}, "t2")
    latest = db.latest_ranking("founder:1")
    assert latest["id"] == rid and latest["subject_version"] == 2 and latest["trace_id"] == "t2"
    assert latest["candidates"] == [{"key": "investor:b", "version": 3}]
    assert latest["payload"]["matches"] == [{"key": "investor:b"}] and latest["created_at"]


# --- lookups ------------------------------------------------------------------------------------------------------

def test_sessions_with_a_caller_token(db):
    user = db.create_user("founder", "Alex", "a@b.c")
    expires = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    assert db.create_session(user["id"], token="tok-1", expires_at=expires) == "tok-1"
    assert db.session_user("tok-1")["id"] == user["id"]
    assert len(db.create_session(user["id"])) == 64  # default: a new random token
    db.delete_session("tok-1")
    assert db.session_user("tok-1") is None


def test_user_by_id_investor_name_and_founder_link(db):
    inv = db.create_user("investor", "Sam", "s@b.c")
    db.set_investor_name(inv["id"], "Fjord Ventures")
    assert db.user_by_id(inv["id"])["investorName"] == "Fjord Ventures"
    founder_user = db.create_user("founder", "Alex", "a@b.c")
    record = db.upsert_founder({"profile": {"startupName": "Carbonlens"}, "founderName": "Alex", "email": "a@b.c",
                                "discoverable": True})
    db.link_founder(founder_user["id"], record["id"])
    assert db.user_by_id(founder_user["id"])["founderId"] == record["id"]
    assert db.founder(record["id"])["profile"]["startupName"] == "Carbonlens"
    assert db.founder("missing") is None and db.user_by_id("missing") is None
    with pytest.raises(DbError):
        db.set_investor_name(founder_user["id"], "Not an investor")


def test_search_entities_finds_entities_and_names_in_rounds(db):
    db.upsert_entity({"id": "e1", "name": "Fjord Ventures", "entity_type": "Organization"}, "cala")
    db.upsert_round({"company": "Fjordline Robotics", "announced": "2025-01-02", "leadInvestors": ["Fjord Ventures"],
                     "otherInvestors": ["Nordic Fjord Angels"], "sources": []}, "cala")
    hits = db.search_entities("fjord", limit=10)
    names = [h["name"] for h in hits]
    assert names.count("Fjord Ventures") == 1  # the entity row wins over the same name in rounds
    assert {"Fjord Ventures", "Fjordline Robotics", "Nordic Fjord Angels"} == set(names)
    assert next(h for h in hits if h["name"] == "Fjord Ventures")["id"] == "e1"
    assert all(h["id"] and h["entity_type"] for h in hits)
    assert len(db.search_entities("fjord", limit=2)) == 2
    assert db.search_entities("", limit=5) == []


def test_country_is_stored_and_rounds_filter_by_industry_stage_country(db):
    rows = [{"company": "A", "round_date": "2025-01-10", "stage": "Seed", "sector": "Climate tech", "country": "France",
             "investors": "X (lead)"},
            {"company": "B", "round_date": "2025-02-10", "stage": "Series A", "sector": "Fintech", "country": "UK",
             "investors": "Y (lead)"},
            {"company": "C", "round_date": "2024-01-10", "stage": "seed", "sector": "AI / climate", "country": "uk",
             "investors": "Z"}]
    for r in rows:
        db.upsert_round(deal_from_row(r), "cala")
    assert deal_from_row(rows[0])["country"] == "France"
    assert db.rounds(company="A")[0]["country"] == "France"
    assert {d["company"] for d in db.rounds(industry_terms=["climate"])} == {"A", "C"}
    assert {d["company"] for d in db.rounds(stages=["seed"])} == {"A", "C"}
    assert {d["company"] for d in db.rounds(stages=["series-a"])} == {"B"}
    assert {d["company"] for d in db.rounds(countries=["UK"])} == {"B", "C"}
    assert {d["company"] for d in db.rounds(industry_terms=["climate"], countries=["uk"], since="2024-06-01")} == set()


# --- migration ----------------------------------------------------------------------------------------------------

def _make_v1(path):
    """A v2 file taken back to v1: no country column, no jobs/rankings tables, user_version 1."""
    LeadlineDb(path).upsert_round({"company": "Old", "announced": "2024-05-05", "round": "seed",
                                   "leadInvestors": ["Q"], "otherInvestors": [], "sources": []}, "cala")
    con = sqlite3.connect(path)
    con.execute("ALTER TABLE funding_rounds DROP COLUMN country")
    con.execute("DROP TABLE jobs")
    con.execute("DROP TABLE rankings")
    con.execute("PRAGMA user_version = 1")
    con.commit()
    con.close()


def test_opening_a_v1_file_migrates_it_without_losing_rows(tmp_path):
    path = tmp_path / "v1.db"
    _make_v1(path)
    db = LeadlineDb(path)
    con = sqlite3.connect(path)
    assert con.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 2
    assert "country" in {r[1] for r in con.execute("PRAGMA table_info(funding_rounds)")}
    con.close()
    assert db.rounds(company="Old")[0]["round"] == "seed"
    db.upsert_round({"company": "New", "announced": "2025-05-05", "country": "Spain", "leadInvestors": [],
                     "otherInvestors": [], "sources": []}, "cala")  # writes work after the migration
    assert db.rounds(company="New")[0]["country"] == "Spain"
    assert db.enqueue_job("profile", "founder:1")["status"] == "queued"


@pytest.mark.skipif(not REAL_DB.is_file(), reason="no leadline/data/leadline.db")
def test_the_real_v1_database_migrates_on_a_copy(tmp_path):
    copy = tmp_path / "leadline.db"
    shutil.copy(REAL_DB, copy)
    before = sqlite3.connect(copy).execute("SELECT COUNT(*) FROM profiles").fetchone()[0]
    db = LeadlineDb(copy)
    con = sqlite3.connect(copy)
    assert con.execute("SELECT COUNT(*) FROM profiles").fetchone()[0] == before
    assert con.execute("PRAGMA user_version").fetchone()[0] == 2
    con.close()
    assert db.jobs_summary()["queued"] == 0


# --- review fixes -------------------------------------------------------------------------------------------------

def test_a_late_finish_from_an_abandoned_attempt_does_not_overwrite_the_retry(db):
    db.enqueue_job("profile", "founder:1")
    first = db.claim_job()
    _age_running_jobs(db, 3600)
    db.requeue_stale(older_than_s=600)
    retry = db.claim_job()
    assert retry["attempts"] == 2
    assert db.finish_job(first["id"], error="late failure", attempt=first["attempts"]) is False
    assert db.job_state("profile", "founder:1")["status"] == "running"  # the retry still owns the job
    assert db.finish_job(retry["id"], attempt=retry["attempts"]) is True
    assert db.job_state("profile", "founder:1")["status"] == "done"
    assert db.finish_job(retry["id"], error="twice", attempt=retry["attempts"]) is False  # finished once only


def test_a_country_sent_as_a_list_or_object_is_stored_as_text(db):
    a = deal_from_row({"company": "A", "round_date": "2025-01-10", "country": ["France", "Germany"]})
    assert a["country"] == "France"
    db.upsert_round(a, "cala")
    db.upsert_round({"company": "B", "announced": "2025-01-11", "country": {"name": "Spain"}, "leadInvestors": [],
                     "otherInvestors": [], "sources": []}, "cala")
    assert db.rounds(company="A")[0]["country"] == "France"
    assert db.rounds(company="B")[0]["country"] == "Spain"


def test_profile_status_is_ready_once_stored_even_after_a_done_job(db):
    job = db.enqueue_job("profile", "founder:1")
    db.claim_job()
    db.put("founder:1", _profile("A"), {"total": 0.5, "parts": {}, "sources": []}, [])
    db.finish_job(job["id"])
    assert db.profile_status("founder:1") == "ready"


def test_blank_filter_terms_are_ignored(db):
    db.upsert_round(deal_from_row({"company": "A", "round_date": "2025-01-10", "sector": "Fintech"}), "cala")
    db.upsert_round(deal_from_row({"company": "B", "round_date": "2025-01-11", "stage": "Seed", "sector": "AI",
                                   "country": "UK"}), "cala")
    assert {d["company"] for d in db.rounds(stages=["-"])} == {"A", "B"}  # no real stage given: no stage filter
    assert {d["company"] for d in db.rounds(industry_terms=[" "])} == {"A", "B"}
    assert {d["company"] for d in db.rounds(countries=["  "])} == {"A", "B"}
    assert {d["company"] for d in db.rounds(countries=[" uk "])} == {"B"}


def test_session_expiry_written_in_other_iso_forms_is_compared_as_a_time(db):
    user = db.create_user("founder", "Alex", "a@b.c")
    later = datetime.now(timezone.utc) + timedelta(hours=2)
    db.create_session(user["id"], token="space", expires_at=later.strftime("%Y-%m-%d %H:%M:%S"))
    db.create_session(user["id"], token="zulu", expires_at=later.strftime("%Y-%m-%dT%H:%M:%S.000Z"))
    earlier = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.create_session(user["id"], token="gone", expires_at=earlier.strftime("%Y-%m-%dT%H:%M:%SZ"))
    assert db.session_user("space")["id"] == user["id"]
    assert db.session_user("zulu")["id"] == user["id"]
    assert db.session_user("gone") is None
    with pytest.raises(DbError):
        db.create_session(user["id"], token="bad", expires_at="next tuesday")


def test_reads_do_not_wait_for_a_writer(db):
    db.enqueue_job("profile", "founder:1")
    db.timeout = 0.2
    writer = sqlite3.connect(db.path, isolation_level=None)
    writer.execute("BEGIN IMMEDIATE")  # the worker in the middle of a write
    try:
        assert db.jobs_summary()["queued"] == 1
        assert db.job_state("profile", "founder:1")["status"] == "queued"
        assert db.profile_status("founder:1") == "building"
        assert db.rounds() == [] and db.latest_ranking("founder:1") is None
        assert db.user_by_id("missing") is None and db.latest_profiles("startup") == []
    finally:
        writer.execute("ROLLBACK")
        writer.close()
