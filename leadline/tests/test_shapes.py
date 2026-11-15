"""leadline/shapes.py: DB rows -> the frontend's exact types, checked against contracts/schemas/ (generated from
frontend/src/lib/**/*.ts by scripts/gen_contract_schemas.sh), and frontend records -> leadline-profile inputs."""
import json
import shutil
import subprocess
from pathlib import Path

import jsonschema
import pytest

from db import LeadlineDb, deal_from_row
import shapes

REPO = Path(__file__).resolve().parents[2]
SCHEMAS = REPO / "contracts" / "schemas"
PROFILE_INPUT = REPO / "leadline" / "plugins" / "leadline-profile" / "input.schema.json"

PERSONA = {"startupName": "Carbonlens", "oneLiner": "Measures and cuts Scope 3 emissions for mid-size manufacturers",
           "sector": "climate", "stage": "seed", "location": "Berlin, Germany", "region": "europe", "raiseEurM": 1.5,
           "competitors": ["Tracely"], "customers": "mid-size manufacturers"}


def check(type_name, value):
    schema = json.loads((SCHEMAS / f"{type_name}.json").read_text())
    jsonschema.Draft7Validator(schema).validate(value)


def fails(type_name, value) -> bool:
    try:
        check(type_name, value)
    except jsonschema.ValidationError:
        return True
    return False


@pytest.fixture
def db(tmp_path):
    db = LeadlineDb(tmp_path / "leadline.db")
    db.upsert_round({"company": "Fractile", "announced": "2025-07-01", "round": None, "industry": None,
                     "companyDescription": None, "amountEurM": None, "leadInvestors": [],
                     "otherInvestors": ["Kindred"],
                     "sources": [{"publisher": "Sifted", "title": "Fractile raises", "url": "https://sifted.eu/x"}]},
                    "cala")
    db.upsert_round({"company": "Mistral AI", "announced": "2023-06-15", "round": "seed", "industry": "AI / LLMs",
                     "companyDescription": "LLMs", "amountEurM": 105.8, "leadInvestors": ["Lightspeed"],
                     "otherInvestors": [], "calaEntityId": "5a55", "sources": []}, "cala")
    db.upsert_fund_close({"investor": "Lightspeed", "fundName": None, "sizeEurM": 500.0, "closed": "2026-01-10"},
                         "cala")
    db.upsert_fund_close({"investor": "Kindred", "fundName": "Kindred III", "sizeEurM": None, "closed": None}, "cala")
    db.upsert_entity({"id": "5a55", "name": "Mistral AI", "entity_type": "Company"}, "cala")
    db.upsert_entity({"id": "nameless", "name": None, "entity_type": None}, "cala")
    return db


def test_schemas_were_generated():
    names = {p.stem for p in SCHEMAS.glob("*.json")}
    assert {"Deal", "FundClose", "CalaEntity", "User", "FounderRecord", "PublicFounder", "Intro", "FounderProfile",
            "ShortlistResponse", "StartupDiligence", "SessionUser"} <= names


def test_raw_db_rows_do_not_match_the_contract(db):
    # The reason shapes.py exists: rows carry provenance and nulls the frontend types do not allow.
    assert fails("Deal", db.rounds()[0])


def test_deal_out_matches_contract(db):
    deals = [shapes.deal_out(r) for r in db.rounds()]
    for d in deals:
        check("Deal", d)
    fractile = next(d for d in deals if d["company"] == "Fractile")
    assert fractile["companyDescription"] == "" and fractile["industry"] == "" and fractile["round"] == ""
    assert fractile["sources"] == [{"publisher": "Sifted", "title": "Fractile raises", "url": "https://sifted.eu/x"}]
    assert "calaEntityId" not in fractile
    assert next(d for d in deals if d["company"] == "Mistral AI")["calaEntityId"] == "5a55"


def test_fund_close_out_matches_contract_and_drops_undated(db):
    out = [shapes.fund_close_out(r) for r in db.fund_closes()]
    kept = [c for c in out if c is not None]
    assert len(kept) == 1 and kept[0]["fundName"] == ""
    for c in kept:
        check("FundClose", c)


def test_entity_out_matches_contract(db):
    for eid in ("5a55", "nameless"):
        check("CalaEntity", shapes.entity_out(db.entity(eid)))


def test_user_out_matches_contract(db):
    founder = shapes.user_out(db.create_user("founder", "Alex", "Alex@Example.com", "salt:hash", is_demo=True))
    investor = shapes.user_out(db.create_user("investor", "Sam", "sam@example.com", investor_name="Fjord Ventures"))
    for u in (founder, investor):
        check("User", u)
    assert "founderId" not in founder and "investorName" not in founder and "isDemo" not in founder
    assert investor["investorName"] == "Fjord Ventures"


def test_founder_public_founder_and_intro_out_match_contract(db):
    row = db.upsert_founder({"profile": PERSONA, "founderName": "Alex", "email": "alex@example.com",
                             "discoverable": True})
    check("FounderRecord", shapes.founder_record_out(row))
    check("PublicFounder", shapes.public_founder_out(row))
    assert "email" not in shapes.public_founder_out(row)
    intro = db.create_intro(row["id"], "Fjord Ventures", "founder-to-investor", "hi")
    check("Intro", shapes.intro_out(intro))


SLUG_CASES = ["Fjord Ventures", "Café Capital!", "  --A&B--  ", "Ølund Partners", "Index  Ventures (EU)", "a16z"]


def test_slugify_matches_typescript_cases():
    assert [shapes.slugify(n) for n in SLUG_CASES[:3]] == ["fjord-ventures", "cafe-capital", "a-b"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_slugify_is_identical_to_frontend_slugify():
    src = (REPO / "frontend" / "src" / "lib" / "leadline" / "types.ts").read_text()
    body = src[src.index("export function slugify"):]
    body = body[:body.index("\n}\n") + 3].replace("export function slugify(name: string): string",
                                                  "function slugify(name)")
    js = body + f"\nconsole.log(JSON.stringify({json.dumps(SLUG_CASES)}.map(slugify)));"
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout
    assert json.loads(out) == [shapes.slugify(n) for n in SLUG_CASES]


def test_profile_keys():
    assert shapes.profile_key_founder("f-1") == "founder:f-1"
    assert shapes.profile_key_investor("Fjord Ventures") == "investor:fjord-ventures"


def test_founder_profile_input_matches_plugin_schema(db):
    record = db.upsert_founder({"profile": PERSONA, "founderName": "Alex", "email": "a@b.c", "discoverable": True})
    value = shapes.founder_profile_input(record, db.rounds(company="Carbonlens"), as_of="2026-11-14")
    jsonschema.Draft7Validator(json.loads(PROFILE_INPUT.read_text())).validate(value)
    assert value["user"] == {"id": f"founder:{record['id']}", "kind": "startup", "name": "Carbonlens",
                             "website": None,
                             "fields": {k: v for k, v in PERSONA.items() if k != "startupName"}}
    assert value["cala_facts"] == [] and value["as_of"] == "2026-11-14"


def test_investor_profile_input_rows_round_trip_to_the_same_deals(db):
    rounds = db.rounds(investor="Lightspeed")
    value = shapes.investor_profile_input("Lightspeed", rounds, as_of="2026-11-14")
    jsonschema.Draft7Validator(json.loads(PROFILE_INPUT.read_text())).validate(value)
    assert value["user"]["id"] == "investor:lightspeed" and value["user"]["kind"] == "investor"
    (row,) = value["cala_facts"]
    assert row["investors"] == "Lightspeed (lead)" and row["stage"] == "seed" and row["sector"] == "AI / LLMs"
    back = deal_from_row(row)
    assert (back["company"], back["announced"], back["leadInvestors"]) == ("Mistral AI", "2023-06-15", ["Lightspeed"])
    assert back["amountEurM"] == pytest.approx(105.8)


def test_cala_facts_are_capped_at_100(db):
    many = [dict(db.rounds()[0], company=f"C{i}") for i in range(150)]
    assert len(shapes.investor_profile_input("Kindred", many)["cala_facts"]) == 100


# --- round trips the review found broken: big/small amounts, month/year-only dates, commas in names -------------

def _round_trip(db, deal):
    db.upsert_round(deal, "cala")
    stored = next(r for r in db.rounds() if r["company"] == deal["company"])
    back = deal_from_row(shapes.deal_to_cala_row(stored))
    return stored, back


@pytest.mark.parametrize("amount", [20000.0, 105.8, 1234.5678, 0.0001])
def test_amounts_round_trip(db, amount):
    stored, back = _round_trip(db, {"company": "Bigco", "announced": "2025-03-04", "amountEurM": amount,
                                    "leadInvestors": ["A"], "otherInvestors": [], "sources": []})
    assert back["amountEurM"] == pytest.approx(stored["amountEurM"])


@pytest.mark.parametrize("raw,text", [("Jun 2023", "Jun 2023"), ("2023", "2023"), ("2023-06-15", "2023-06-15"),
                                      ("2023-07-01", "2023-07-01")])
def test_dates_keep_their_precision_and_id(db, raw, text):
    deal = deal_from_row({"company": "Acme", "round_date": raw, "stage": "seed", "investors": "A (lead)"})
    stored, back = _round_trip(db, deal)
    assert shapes.deal_to_cala_row(stored)["round_date"] == text
    assert (back["id"], back["announced"]) == (stored["id"], stored["announced"])


def test_commas_inside_investor_names_do_not_split_them(db):
    stored, back = _round_trip(db, {"company": "Acme", "announced": "2025-01-02", "leadInvestors": ["Smith, Jones"],
                                    "otherInvestors": ["B"], "sources": []})
    assert back["leadInvestors"] == ["Smith Jones"] and back["otherInvestors"] == ["B"]


def test_schemas_are_current_for_the_frontend_sources():
    """gen_contract_schemas.sh stores a hash of the TS files it read; a TS change without regenerating fails here."""
    import hashlib
    stamp = json.loads((SCHEMAS / "sources.json").read_text())
    for rel, digest in stamp.items():
        assert hashlib.sha256((REPO / rel).read_bytes()).hexdigest() == digest, f"{rel} changed: regenerate schemas"
    assert not list(SCHEMAS.glob(".*.err"))
