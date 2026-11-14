"""leadline/db.py: one SQLite file (WAL) shaped like the frontend's data (types.ts, match-types.ts, server/db.ts).
Sourced rows carry provenance; computed snapshots list their heuristic (made-up) fields; profiles share the file."""
import sqlite3
import threading

import pytest

from db import SNAPSHOT_TABLES, SYNTHETIC_FIELDS, DbError, LeadlineDb, deal_from_row
from profiles import get_or_build

UUID = "5a55e4a2-7bae-49ae-8893-fb400096c36b"
DEAL = {"company": "Carbonlens", "companyDescription": "Carbon accounting for SMEs", "industry": "climate",
        "round": "seed", "amountEurM": 3.5, "announced": "2025-03-15", "leadInvestors": ["Fjord Ventures"],
        "otherInvestors": ["Angel A"], "sources": [{"publisher": "TechCrunch", "title": "Carbonlens raises",
                                                   "url": "https://tc.com/carbonlens"}]}


@pytest.fixture
def db(tmp_path):
    return LeadlineDb(tmp_path / "leadline.db")


def test_wal_foreign_keys_and_every_table(db):
    con = sqlite3.connect(db.path)
    assert con.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert con.execute("PRAGMA user_version").fetchone()[0] >= 1
    names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")}
    expected = {"entities", "funding_rounds", "fund_closes", "evidence_sources", "agent_profiles", "users",
                "sessions", "founders", "intros", *SNAPSHOT_TABLES.values()}
    assert expected <= names
    assert {"shortlist_runs", "twins_reports", "investor_briefs", "investor_theses", "fit_reports", "signals",
            "diligence_reports", "outreach_drafts"} <= set(SNAPSHOT_TABLES.values())


def test_round_round_trip_keeps_frontend_shape_and_provenance(db):
    rid = db.upsert_round(DEAL, provider="cala", source_url="https://cala.ai/q/1", trace_id="t1")
    assert rid == "carbonlens:2025-03-15"  # the frontend's Deal.id
    [deal] = db.rounds(company="Carbonlens")
    assert {k: deal[k] for k in DEAL} == DEAL
    assert deal["id"] == rid
    p = deal["provenance"]
    assert p["provider"] == "cala" and p["sourceUrl"] == "https://cala.ai/q/1" and p["traceId"] == "t1"
    assert p["fetchedAt"] and p["synthetic"] is False


def test_upsert_keeps_known_values_and_dedupes_sources(db):
    db.upsert_round(DEAL, provider="cala")
    db.upsert_round({**DEAL, "amountEurM": None, "companyDescription": None}, provider="cala")
    [deal] = db.rounds()
    assert deal["amountEurM"] == 3.5 and deal["companyDescription"] == DEAL["companyDescription"]
    assert len(deal["sources"]) == 1


def test_round_filters(db):
    db.upsert_round(DEAL, provider="cala")
    db.upsert_round({**DEAL, "company": "Other", "announced": "2023-01-15", "leadInvestors": ["Northwind"],
                     "otherInvestors": ["Fjord Ventures"]}, provider="cala")
    assert {d["company"] for d in db.rounds(investor="Fjord Ventures")} == {"Carbonlens", "Other"}
    assert [d["company"] for d in db.rounds(since="2024-01-01")] == ["Carbonlens"]
    assert [d["company"] for d in db.rounds(investor="northwind")] == ["Other"]  # case-insensitive


def test_provider_must_be_known(db):
    with pytest.raises(DbError):
        db.upsert_round(DEAL, provider="made_up")


def test_simulated_rows_are_marked_synthetic(db):
    db.upsert_round(DEAL, provider="simulated")
    assert db.rounds()[0]["provenance"]["synthetic"] is True


def test_fund_close_and_entity_round_trip(db):
    db.upsert_fund_close({"investor": "Fjord Ventures", "fundName": "Fjord III", "sizeEurM": 120.0,
                          "closed": "2025-06-01", "sources": DEAL["sources"]}, provider="cala", trace_id="t2")
    [close] = db.fund_closes(investor="Fjord Ventures")
    assert close["fundName"] == "Fjord III" and close["sizeEurM"] == 120.0 and close["sources"] == DEAL["sources"]
    assert close["provenance"]["traceId"] == "t2"
    db.upsert_entity({"id": UUID, "name": "Mistral AI", "entity_type": "Company"}, provider="cala")
    assert db.entity(UUID)["name"] == "Mistral AI"


def test_snapshots_carry_synthetic_fields(db):
    payload = {"mode": "live", "investors": [{"name": "Fjord", "score": 71}]}
    sid = db.put_snapshot("shortlist", "profile-hash", payload, mode="live", trace_id="t3")
    snap = db.latest_snapshot("shortlist", "profile-hash")
    assert snap["id"] == sid and snap["payload"] == payload and snap["traceId"] == "t3"
    assert snap["syntheticFields"] == SYNTHETIC_FIELDS["shortlist"] and "investors[].score" in snap["syntheticFields"]
    assert snap["synthetic"] is False


def test_simulated_snapshot_is_wholly_synthetic_and_latest_wins(db):
    db.put_snapshot("fit", "k", {"score": 10}, mode="live")
    db.put_snapshot("fit", "k", {"score": 20}, mode="simulated")
    snap = db.latest_snapshot("fit", "k")
    assert snap["payload"] == {"score": 20} and snap["synthetic"] is True and snap["syntheticFields"] == ["*"]
    assert db.latest_snapshot("fit", "missing") is None


def test_unknown_snapshot_kind_or_mode_is_refused(db):
    with pytest.raises(DbError):
        db.put_snapshot("horoscope", "k", {}, mode="live")
    with pytest.raises(DbError):
        db.put_snapshot("fit", "k", {}, mode="guess")


# --- Cala results ----------------------------------------------------------------------------------------------

FRONTEND_ROW = {"company": "Carbonlens", "company_description": "Carbon accounting", "industry": "Climate",
                "round_type": "Seed", "amount": "€3.5M", "announced_date": "March 2025",
                "lead_investors": "Fjord Ventures", "other_investors": "Angel A, Angel B"}
INGEST_ROW = {"amount": "115", "company": "Mistral AI", "country": "France", "currency": "$",
              "investors": "Lightspeed Venture Partners (lead), Xavier Niel", "round_date": "Jun 2023",
              "sector": "AI / LLMs", "stage": "seed"}


def test_deal_from_frontend_columns():
    d = deal_from_row(FRONTEND_ROW)
    assert d["id"] == "carbonlens:2025-03-15:seed" and d["announced"] == "2025-03-15"  # month only -> the 15th
    assert d["amountEurM"] == 3.5 and d["round"] == "Seed" and d["industry"] == "Climate"
    assert d["leadInvestors"] == ["Fjord Ventures"] and d["otherInvestors"] == ["Angel A", "Angel B"]


def test_deal_from_ingest_columns():
    d = deal_from_row(INGEST_ROW)
    assert d["company"] == "Mistral AI" and d["announced"] == "2023-06-15" and d["round"] == "seed"
    assert d["amountEurM"] == pytest.approx(115 * 0.92)  # USD at the frontend's rate
    assert d["leadInvestors"] == ["Lightspeed Venture Partners"] and d["otherInvestors"] == ["Xavier Niel"]


def test_rows_without_company_or_date_are_skipped():
    assert deal_from_row({"company": "X"}) is None
    assert deal_from_row({"announced_date": "2024"}) is None
    assert deal_from_row({"company": "X", "announced_date": "2024"})["announced"] == "2024-07-01"


def test_record_cala_query_stores_rounds_and_entities(db):
    reply = {"results": [FRONTEND_ROW, INGEST_ROW, {"company": "No date"}],
             "entities": [{"id": UUID, "name": "Mistral AI", "entity_type": "Company", "mentions": ["x"]}]}
    n = db.record_cala("knowledge_query", {"input": "rounds"}, reply, trace_id="t4")
    assert n == {"rounds": 2, "entities": 1, "sources": 0}
    assert {d["company"] for d in db.rounds()} == {"Carbonlens", "Mistral AI"}
    assert db.rounds(company="Mistral AI")[0]["provenance"]["traceId"] == "t4"
    assert db.entity(UUID)["entity_type"] == "Company"


def test_record_cala_search_attaches_sources_to_matching_rounds(db):
    db.upsert_round(DEAL, provider="cala")
    reply = {"explainability": [{"content": "Carbonlens raised a seed round", "references": ["r1"]}],
             "context": [{"id": "r1", "content": "Carbonlens raised EUR 3.5M in March 2025.",
                          "origins": [{"source": {"name": "Sifted"},
                                       "document": {"name": "Carbonlens seed", "url": "https://sifted.eu/c"}}]}]}
    n = db.record_cala("knowledge_search", {"input": "Carbonlens"}, reply)
    assert n["sources"] == 1
    urls = {s["url"] for s in db.rounds()[0]["sources"]}
    assert urls == {"https://tc.com/carbonlens", "https://sifted.eu/c"}


def test_record_cala_entity_replies(db):
    db.record_cala("entity_search", {"name": "Mistral"}, {"entities": [{"id": UUID, "name": "Mistral AI",
                                                                         "entity_type": "Company"}]})
    db.record_cala("entity_get", {"id": UUID}, {"id": UUID, "name": "Mistral AI", "entity_type": "Company",
                                                "description": "LLM lab"})
    assert db.entity(UUID)["description"] == "LLM lab"


def test_record_cala_works_as_the_venus_hook(tmp_path, db):
    import httpx

    from venus.cala import Cala, cala_tools
    reply = {"results": [FRONTEND_ROW], "entities": []}
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=reply)))
    cala = Cala(api_key="k", http_client=client, cache_dir=tmp_path / "cala", environ={},
                on_result=db.cala_hook(trace_id="run-1"))
    out = {t.name: t for t in cala_tools(cala)}["cala_knowledge_query"].fn({"question": "q"})
    assert "warning" not in out
    assert db.rounds()[0]["provenance"]["traceId"] == "run-1"


# --- profiles share the file -------------------------------------------------------------------------------------

def test_profiles_live_in_the_same_file(db):
    from test_profiles import CALA, USER, profile_output
    calls = []

    def run(input):
        calls.append(input)
        return profile_output()
    first = get_or_build(db, USER, run, cala_facts=CALA)
    again = get_or_build(db, USER, run, cala_facts=CALA)
    assert first["version"] == again["version"] == 1 and len(calls) == 1
    con = sqlite3.connect(db.path)
    assert con.execute("SELECT COUNT(*) FROM agent_profiles").fetchone()[0] == 1


# --- app data (frontend server/db.ts) ----------------------------------------------------------------------------

def test_users_sessions_founders(db):
    founder = db.upsert_founder({"profile": {"startupName": "Carbonlens", "sector": "climate"},
                                 "founderName": "Ana", "email": "ana@example.com", "discoverable": True})
    user = db.create_user(role="founder", name="Ana", email="Ana@Example.com", password_hash="s:h",
                          founder_id=founder["id"])
    assert db.user_by_email("ana@example.com")["id"] == user["id"]
    with pytest.raises(DbError):
        db.create_user(role="founder", name="Dup", email="ana@example.com", password_hash="")
    token = db.create_session(user["id"])
    assert db.session_user(token)["id"] == user["id"]
    assert db.session_user("nope") is None
    assert [f["founderName"] for f in db.discoverable_founders()] == ["Ana"]
    db.upsert_founder({**founder, "discoverable": False})
    assert db.discoverable_founders() == []


def test_expired_session_is_refused(db):
    user = db.create_user(role="investor", name="I", email="i@example.com", password_hash="",
                          investor_name="Fjord Ventures")
    token = db.create_session(user["id"], days=-1)
    assert db.session_user(token) is None


def test_demo_users_are_flagged(db):
    user = db.create_user(role="founder", name="Demo", email="demo-founder@leadline.local", password_hash="",
                          is_demo=True)
    assert db.user_by_email("demo-founder@leadline.local")["isDemo"] is True and user["isDemo"] is True


def test_intro_dedupe_and_only_the_recipient_responds(db):
    founder = db.upsert_founder({"profile": {}, "founderName": "Ana", "email": "a@x.com", "discoverable": True})
    fuser = db.create_user(role="founder", name="Ana", email="a@x.com", password_hash="", founder_id=founder["id"])
    iuser = db.create_user(role="investor", name="Ivo", email="i@x.com", password_hash="",
                           investor_name="Fjord Ventures")
    other = db.create_user(role="investor", name="Olga", email="o@x.com", password_hash="", investor_name="Other")
    a = db.create_intro(founder["id"], "Fjord Ventures", "founder-to-investor", "hi")
    b = db.create_intro(founder["id"], "Fjord Ventures", "founder-to-investor", "hi again")
    assert a["id"] == b["id"] and a["status"] == "pending"
    with pytest.raises(DbError):
        db.respond_intro(a["id"], fuser["id"], "accepted")  # the sender can't answer
    with pytest.raises(DbError):
        db.respond_intro(a["id"], other["id"], "accepted")  # another fund can't either
    done = db.respond_intro(a["id"], iuser["id"], "passed", pass_reason="Too early for us")
    assert done["status"] == "passed" and done["passReason"] == "Too early for us" and done["respondedAt"]
    with pytest.raises(DbError):
        db.respond_intro(a["id"], iuser["id"], "accepted")  # already answered
    c = db.create_intro(founder["id"], "Fjord Ventures", "investor-to-founder", "")
    assert c["id"] != a["id"]
    assert db.respond_intro(c["id"], fuser["id"], "accepted")["status"] == "accepted"
    assert {i["id"] for i in db.intros(founder_id=founder["id"])} == {a["id"], c["id"]}


def test_concurrent_writers_lose_nothing(tmp_path):
    path = tmp_path / "shared.db"
    LeadlineDb(path)
    errors = []

    def write(n):
        try:
            mine = LeadlineDb(path)
            for i in range(20):
                mine.upsert_round({**DEAL, "company": f"C{n}-{i}"}, provider="cala")
        except Exception as e:  # pragma: no cover - reported below
            errors.append(e)
    threads = [threading.Thread(target=write, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and len(LeadlineDb(path).rounds()) == 80


# --- phase 8 review fixes ---------------------------------------------------------------------------------------

def test_rounds_with_filled_in_dates_keep_their_own_ids(db):
    seed = deal_from_row({"company": "Acme", "announced_date": "2024", "round_type": "Seed"})
    series_a = deal_from_row({"company": "Acme", "announced_date": "2024", "round_type": "Series A"})
    assert seed["id"] != series_a["id"] and seed["announced"] == series_a["announced"] == "2024-07-01"
    exact = deal_from_row({"company": "Acme", "announced_date": "2024-03-02", "round_type": "Seed"})
    assert exact["id"] == "acme:2024-03-02"  # an exact date keeps the frontend's Deal.id
    db.upsert_round(seed, provider="cala")
    db.upsert_round(series_a, provider="cala")
    assert {d["round"] for d in db.rounds(company="Acme")} == {"Seed", "Series A"}


def test_simulated_data_never_overwrites_real_data(db):
    db.upsert_round(DEAL, provider="cala", source_url="https://cala.ai/q/1")
    db.upsert_round({**DEAL, "amountEurM": 99.0, "sources": []}, provider="simulated")
    [deal] = db.rounds()
    assert deal["amountEurM"] == 3.5 and deal["provenance"]["provider"] == "cala"
    assert deal["provenance"]["synthetic"] is False


def test_real_data_replaces_a_simulated_row_whole(db):
    db.upsert_round({**DEAL, "industry": "made up", "sources": [{"publisher": "sim", "title": "t",
                                                                "url": "https://example.com/simulated/x"}]},
                    provider="simulated", source_url="https://example.com/simulated")
    db.upsert_round({**DEAL, "industry": None, "sources": []}, provider="cala")
    [deal] = db.rounds()
    assert deal["provenance"]["provider"] == "cala" and deal["provenance"]["sourceUrl"] is None
    assert deal["industry"] is None and deal["sources"] == []  # nothing simulated survives under a real label


def test_entities_and_funds_follow_the_same_provenance_rule(db):
    db.upsert_entity({"id": UUID, "name": "Real"}, provider="cala")
    db.upsert_entity({"id": UUID, "name": "Fake"}, provider="simulated")
    assert db.entity(UUID)["name"] == "Real"
    close = {"investor": "Fjord", "fundName": "III", "closed": "2025-01-01"}
    db.upsert_fund_close({**close, "sizeEurM": 1.0}, provider="simulated")
    db.upsert_fund_close({**close, "sizeEurM": None}, provider="cala")
    [c] = db.fund_closes()
    assert c["sizeEurM"] is None and c["provenance"]["provider"] == "cala"
