"""scripts/seed_db.py: seed the Leadline DB from the cached Cala pull. No keys, no network: a stub http client that
counts and refuses every Cala request, and the offline fake model for --build.

    cd tests/integration && ../../venus/.venv/bin/python -m pytest -q test_seed_db.py
"""
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT / "leadline", ROOT / "app"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

spec = importlib.util.spec_from_file_location("seed_db", ROOT / "scripts" / "seed_db.py")
seed_db = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed_db)

from db import LeadlineDb  # noqa: E402

REAL_CACHE = ROOT / "app" / "data" / "cache"
INJECTED = ROOT / "leadline" / "agent"
FOUNDER_PROFILE = jsonschema.Draft7Validator(json.loads((ROOT / "contracts" / "schemas" /
                                                         "FounderProfile.json").read_text()))
ROWS = [
    {"amount": "130", "company": "Proxima Fusion", "country": "Germany", "currency": "€",
     "investors": "redalpine (lead)", "round_date": "Jun 2025", "sector": "Fusion energy", "stage": "Series A"},
    {"amount": "46", "company": "VSORA", "country": "France", "currency": "$", "investors": "Otium (lead), Kima",
     "round_date": "2025", "sector": "AI chips", "stage": "Series A"},
    {"amount": "12", "company": "Seva Money", "country": "UK", "currency": "£", "investors": "Seedcamp, Kima",
     "round_date": "2025", "sector": "Fintech / Remittances", "stage": "seed"},
    {"amount": "5", "company": "shaka", "country": "UK", "currency": "$", "investors": "Not disclosed",
     "round_date": "2025", "sector": "Telecom / eSIM", "stage": "seed"},
    {"amount": "3", "company": "Nowhere Co", "country": "Brazil", "currency": "$", "investors": "Not disclosed",
     "round_date": "2025", "sector": "Fintech", "stage": "seed"},
]
ENTITIES = [{"id": "e-redalpine", "name": "redalpine", "entity_type": "Organization"}]


class CountingNoNetwork:
    """Counts every Cala request and refuses it."""

    def __init__(self):
        self.calls = 0

    def request(self, method, url, **kwargs):
        self.calls += 1
        raise AssertionError(f"Cala request made: {method} {url}")


@pytest.fixture
def cache(tmp_path, monkeypatch):
    """A Cala cache holding one reply for the seed's query."""
    monkeypatch.setattr(seed_db, "QUERIES", ["test query"])
    client = seed_db.cala_client(tmp_path / "cache", CountingNoNetwork())
    path = client._cache_path("POST", f"{client.base_url}/v1/knowledge/query", None,
                              {"input": "test query", "return_entities": True})
    path.write_text(json.dumps({"results": ROWS, "entities": ENTITIES}))
    return tmp_path / "cache"


def run(db_path, cache_dir, *extra, http=None, model=None, capsys=None):
    http = http or CountingNoNetwork()
    code = seed_db.main(["--db", str(db_path), "--cache-dir", str(cache_dir), *extra], cala_http=http, model=model,
                        environ={})
    report = json.loads(capsys.readouterr().out) if capsys else None
    return code, report, http


def test_seed_stores_rounds_accounts_and_queues_one_profile_job_each(tmp_path, cache, capsys):
    code, report, http = run(tmp_path / "l.db", cache, capsys=capsys)
    assert code == 0 and http.calls == 0 and report["cala_calls"] == 0
    db = LeadlineDb(tmp_path / "l.db")
    assert report["rounds"] == len(db.rounds()) == 5 and report["entities"] == 1
    assert {d["company"] for d in db.rounds()} == {r["company"] for r in ROWS}
    assert "cala" in db.data_providers()

    # founders: only companies whose sector and country map to the frontend's enums
    assert sorted(report["founders"]) == ["Proxima Fusion", "Seva Money", "VSORA"]
    assert {s["company"]: s["reason"] for s in report["skipped"]} == {
        "shaka": "sector 'Telecom / eSIM' is none of climate, fintech, ai, health, saas",
        "Nowhere Co": "country 'Brazil' is in none of europe, nordics, uk, dach"}
    records = db.discoverable_founders()
    by_name = {f["profile"]["startupName"]: f["profile"] for f in records}
    assert by_name["Proxima Fusion"] == {
        "startupName": "Proxima Fusion", "oneLiner": "Fusion energy company in Germany", "sector": "climate",
        "stage": "series-a", "location": "Germany", "region": "dach", "raiseEurM": 130.0, "competitors": [],
        "customers": ""}
    assert by_name["Seva Money"]["region"] == "uk" and by_name["Seva Money"]["sector"] == "fintech"
    for profile in by_name.values():
        FOUNDER_PROFILE.validate(profile)
    for record in records:
        user = db.user_by_email(record["email"])
        assert user["founderId"] == record["id"] and user["isDemo"] is True

    # investors: leads first, then others by rounds named in; "Not disclosed" is nobody
    assert report["investors"] == ["Otium", "redalpine", "Kima", "Seedcamp"]
    assert "Fjord Ventures" in db.investor_names() and "Otium" in db.investor_names()

    # the two frontend demo accounts
    demo_f = db.user_by_email("demo-founder@leadline.local")
    assert db.founder(demo_f["founderId"])["profile"] == seed_db.DEMO_PERSONA
    assert db.user_by_email("demo-investor@leadline.local")["investorName"] == "Fjord Ventures"

    accounts = 3 + 4 + 2
    assert report["accounts_created"] == accounts and report["jobs_queued"] == accounts
    assert db.jobs_summary() == {"queued": accounts, "running": 0, "done": 0, "failed": 0}
    est = report["estimate"]
    assert est["profile_jobs"] == accounts and est["rank_jobs"] == accounts and est["cala_calls"] == 0
    assert est["model_calls_max"] > 0 and est["context_dev_calls_max"] > 0


def test_a_rerun_adds_nothing(tmp_path, cache, capsys):
    run(tmp_path / "l.db", cache, capsys=capsys)
    _, report, http = run(tmp_path / "l.db", cache, capsys=capsys)
    assert http.calls == 0
    assert report["accounts_created"] == 0 and report["jobs_queued"] == 0
    db = LeadlineDb(tmp_path / "l.db")
    assert len(db.rounds()) == 5 and db.jobs_summary()["queued"] == 9
    assert sqlite3.connect(tmp_path / "l.db").execute("SELECT COUNT(*) FROM users").fetchone()[0] == 9


def test_caps_and_dry_run(tmp_path, cache, capsys):
    _, report, _ = run(tmp_path / "l.db", cache, "--max-founders", "1", "--max-investors", "2", "--dry-run",
                       capsys=capsys)
    assert report["dry_run"] is True and report["founders"] == ["VSORA"]  # newest round first
    assert report["investors"] == ["Otium", "redalpine"] and report["jobs_queued"] == 1 + 2 + 2
    db = LeadlineDb(tmp_path / "l.db")
    assert db.rounds() == [] and db.jobs_summary()["queued"] == 0  # nothing written


def test_an_uncached_query_stops_without_calling_cala(tmp_path, cache, capsys, monkeypatch):
    monkeypatch.setattr(seed_db, "QUERIES", ["test query", "not cached"])
    code, _, http = run(tmp_path / "l.db", cache)
    assert code == 2 and http.calls == 0
    assert "not cached" in capsys.readouterr().err


@pytest.mark.skipif(not REAL_CACHE.is_dir(), reason="no app/data/cache (the real Cala pull)")
def test_the_real_cached_pull_stores_21_rounds(tmp_path, capsys):
    code, report, http = run(tmp_path / "l.db", REAL_CACHE, "--dry-run", capsys=capsys)
    assert code == 0 and http.calls == 0 and report["rows"] == 21
    assert report["rounds"] == 20  # Dronamics' date is a range ("2025–2026"): no single date, no round
    assert len(report["founders"]) == 10 and len(report["investors"]) == 10


@pytest.mark.skipif(not (INJECTED / "leadline_agent" / "__init__.py").is_file(),
                    reason="no injected agent at leadline/agent (run scripts/inject_agent.sh)")
def test_build_runs_every_job_and_ranks_every_account(tmp_path, cache, capsys):
    saved_path = list(sys.path)
    saved = {m: sys.modules.pop(m) for m in list(sys.modules) if m.split(".")[0] == "leadline_agent"}
    try:
        import serve
        model = serve.offline_model(INJECTED)
        code, report, http = run(tmp_path / "l.db", cache, "--build", model=model, capsys=capsys)
    finally:
        for m in [m for m in sys.modules if m.split(".")[0] == "leadline_agent"]:
            del sys.modules[m]
        sys.modules.update(saved)
        sys.path[:] = saved_path
    assert code == 0 and http.calls == 0
    db = LeadlineDb(tmp_path / "l.db")
    summary = db.jobs_summary()
    assert summary["failed"] == 0 and summary["queued"] == 0 and summary["done"] == 18  # 9 profiles, 9 ranks
    assert report["build"] == {"done": 18, "failed": 0}
    keys = [f"founder:{f['id']}" for f in db.discoverable_founders()] + \
        [f"investor:{seed_db.shapes.slugify(n)}" for n in db.investor_names()]
    assert len(keys) == 9 and all(db.latest_ranking(k) is not None for k in keys)


# --- review fixes -------------------------------------------------------------------------------------------------

def test_dry_run_leaves_the_database_file_untouched(tmp_path, cache, capsys):
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE marker (x)")
    con.commit()
    con.close()
    before = path.read_bytes()
    _, report, _ = run(path, cache, "--dry-run", capsys=capsys)
    assert report["jobs_queued"] == 9
    assert path.read_bytes() == before and not (tmp_path / "old.db-wal").exists()


def test_a_failed_profile_is_queued_again_on_a_rerun(tmp_path, cache, capsys):
    run(tmp_path / "l.db", cache, capsys=capsys)
    db = LeadlineDb(tmp_path / "l.db")
    job = db.claim_job()
    db.finish_job(job["id"], error="model_unavailable: down")
    _, report, _ = run(tmp_path / "l.db", cache, capsys=capsys)
    assert report["jobs_queued"] == 1 and db.job_state("profile", job["subject_key"])["status"] == "queued"


def test_names_with_the_same_slug_make_one_account(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(seed_db, "QUERIES", ["q"])
    rows = [{"company": "Alicia (InsurTech)", "country": "UK", "sector": "Insurance", "stage": "seed",
             "round_date": "2025", "investors": "SeedCamp (lead)", "amount": "2", "currency": "€"},
            {"company": "Alicia InsurTech", "country": "UK", "sector": "Insurance", "stage": "seed",
             "round_date": "2024", "investors": "Seedcamp", "amount": "1", "currency": "€"}]
    client = seed_db.cala_client(tmp_path / "c", CountingNoNetwork())
    client._cache_path("POST", f"{client.base_url}/v1/knowledge/query", None,
                       {"input": "q", "return_entities": True}).write_text(json.dumps({"results": rows}))
    _, report, _ = run(tmp_path / "l.db", tmp_path / "c", capsys=capsys)
    assert report["founders"] == ["Alicia (InsurTech)"] and report["investors"] == ["SeedCamp"]
    assert report["accounts_created"] == 2 + 2 and report["jobs_queued"] == 4


def test_guessed_fields_are_reported_and_late_stages_map_to_series_b():
    deal = {"company": "Big", "industry": "Fintech", "round": "Series C", "country": "UK", "amountEurM": None,
            "companyDescription": "Payments for shops", "announced": "2025-01-01"}
    profile, assumed = seed_db.founder_profile(deal)
    assert profile["stage"] == "series-b" and profile["raiseEurM"] == 1.0
    assert profile["oneLiner"] == "Payments for shops"
    assert {(a["field"], a["value"]) for a in assumed} == {("stage", "Series C"), ("raiseEurM", None)}


def test_caps_are_reported(tmp_path, cache, capsys):
    _, report, _ = run(tmp_path / "l.db", cache, "--max-founders", "1", "--max-investors", "1", "--dry-run",
                       capsys=capsys)
    assert report["left_out"] == {"founders": 2, "investors": 3}


def test_build_turns_live_cala_off(tmp_path, monkeypatch):
    import jobs
    seen = {}

    def fake_make_agents(environ=None, agent_root=None, model=None):
        seen.update(environ)
        raise RuntimeError("stop here")
    monkeypatch.setattr(jobs, "make_agents", fake_make_agents)
    with pytest.raises(RuntimeError, match="stop here"):
        seed_db.build(LeadlineDb(tmp_path / "l.db"), {"LEADLINE_LIVE_CALA": "1", "OTHER": "kept"})
    assert "LEADLINE_LIVE_CALA" not in seen and seen["OTHER"] == "kept"
