"""build_cases: Cala rows (as the cached bulk pull returns them) -> time-split leadline-match training cases.
Hide each round, ask for its lead as of the day before; only rows that name a lead become cases. No Cala calls."""
import json

import pytest
from conftest import PLUGINS

from build_cases import (CaseError, build_cases, load_rows, parse_amount, parse_date, parse_investors,
                         parse_rows)
from venus import load_plugin

# Same keys and quirks as the real pull in app/data/cache (2026-11-14): one investors string, "(lead)" inline,
# "Not disclosed", free-text dates, currency symbols, amounts in millions.
ROWS = [
    {"amount": "115", "company": "Mistral AI", "country": "France", "currency": "$",
     "investors": "Lightspeed Venture Partners", "round_date": "Jun 2023", "sector": "AI / LLMs", "stage": "seed"},
    {"amount": "15", "company": "Fractile", "country": "UK", "currency": "$", "investors": "Not disclosed",
     "round_date": "2025", "sector": "AI chips", "stage": "seed"},
    {"amount": "130", "company": "Proxima Fusion", "country": "Germany", "currency": "€",
     "investors": "redalpine (lead)", "round_date": "Jun 2025", "sector": "Fusion energy", "stage": "Series A"},
    {"amount": "28", "company": "Arlequin AI", "country": "France", "currency": "€",
     "investors": "redalpine, OTB Ventures, Bpifrance Defence Innovation Fund", "round_date": "Sep 2026",
     "sector": "AI / Defence", "stage": "Series A"},
    {"amount": "46", "company": "VSORA", "country": "France", "currency": "$", "investors": "Otium (lead)",
     "round_date": "2025", "sector": "AI chips", "stage": "Series A"},
    {"amount": "5", "company": "Seva Money", "country": "UK", "currency": "$",
     "investors": "Blockwall, Revent, Seedcamp, Stride, Ada Ventures", "round_date": "2026",
     "sector": "Fintech / Remittances", "stage": "seed"},
    {"amount": None, "company": "Dronamics", "country": "Bulgaria", "currency": None,
     "investors": "European Innovation Council, Founders Factory", "round_date": "2025–2026",
     "sector": "Logistics / Drones", "stage": "Series A"},
    {"amount": "6.9", "company": "Tumbleweed", "country": "Europe", "currency": "€", "investors": "Not stated",
     "round_date": "Nov 2026", "sector": "Not disclosed", "stage": "seed"},
]


@pytest.fixture(scope="module")
def match_plugin():
    return load_plugin(PLUGINS / "leadline-match")


def test_parse_helpers():
    assert parse_date("Jun 2025") == ("2025-06-01", "2025-06-30")
    assert parse_date("2025") == ("2025-01-01", "2025-12-31")
    assert parse_date("2025–2026") == ("2025-01-01", "2026-12-31")
    assert parse_date("2024-03-10") == ("2024-03-10", "2024-03-10")
    assert parse_date("sometime") is None and parse_date(None) is None
    assert parse_investors("redalpine (lead), OTB Ventures") == [{"name": "redalpine", "role": "lead"},
                                                                  {"name": "OTB Ventures", "role": "unknown"}]
    assert parse_investors("Not disclosed") == [] and parse_investors(None) == []
    assert parse_investors("Orano Ventures/Supernova Invest, BGF")[0]["name"] == "Orano Ventures/Supernova Invest"
    assert parse_amount("4.5", "$") == {"amount": 4_500_000, "currency": "USD"}
    assert parse_amount("130", "€") == {"amount": 130_000_000, "currency": "EUR"}
    assert parse_amount(None, None) is None and parse_amount("lots", "€") is None


def test_parse_rows_ids_and_skips():
    rounds = parse_rows(ROWS)
    assert len(rounds) == len(ROWS)
    proxima = next(r for r in rounds if r["company"] == "Proxima Fusion")
    assert proxima["company_id"] == "c_proxima-fusion" and proxima["stage"] == "series-a"
    assert proxima["sectors"] == ["Fusion energy"] and proxima["investors"][0]["id"] == "i_redalpine"
    assert next(r for r in rounds if r["company"] == "Mistral AI")["sectors"] == ["AI", "LLMs"]


def test_explicit_leads_make_cases(match_plugin):
    cases, report = build_cases(ROWS)
    assert sorted(c["id"] for c in cases) == ["proxima-fusion-2025-06", "vsora-2025"]
    assert report["cases"] == 2 and report["undisclosed"] == 2 and report["no_lead"] >= 3
    for c in cases:
        match_plugin.validate_input(c["input"])
        match_plugin.validate_output(c["expected"])
        leads = [m["candidate_id"] for m in c["expected"]["matches"]]
        assert leads and all(lead in {x["id"] for x in c["input"]["candidates"]} for lead in leads)
        assert c["input"]["subject"]["kind"] == "startup"
        assert c["input"]["request"]["direction"] == "startup_to_investors"
    proxima = next(c for c in cases if c["id"].startswith("proxima"))
    assert proxima["input"]["request"]["as_of"] == "2025-05-31"
    assert [m["candidate_id"] for m in proxima["expected"]["matches"]] == ["i_redalpine"]
    assert proxima["input"]["subject"]["raising"] == {"amount": 130_000_000, "currency": "EUR"}


def test_no_answer_leaks_into_the_input():
    cases, _ = build_cases(ROWS)
    for c in cases:
        text = json.dumps(c["input"]).casefold()
        assert "(lead)" not in text
        as_of = c["input"]["request"]["as_of"]
        for cand in c["input"]["candidates"]:
            for f in cand.get("facts", []):
                assert f.get("date", "") <= as_of, (c["id"], cand["id"], f)  # only facts known before the round


def test_history_before_as_of_is_kept_as_facts():
    rows = ROWS + [{"amount": "3", "company": "Early Co", "country": "Germany", "currency": "€",
                    "investors": "redalpine (lead)", "round_date": "Jan 2024", "sector": "Energy", "stage": "seed"}]
    cases, _ = build_cases(rows)
    proxima = next(c for c in cases if c["id"].startswith("proxima"))
    red = next(x for x in proxima["input"]["candidates"] if x["id"] == "i_redalpine")
    assert red["last_lead_date"] == "2024-01-01"
    assert any("Early Co" in f.get("quote", "") for f in red["facts"])
    assert not red.get("stages") and not red.get("sectors")  # history is evidence, not a stated focus


def test_sole_investor_rule_is_opt_in():
    cases, _ = build_cases(ROWS, lead_rule="explicit_or_sole")
    assert "mistral-ai-2023-06" in {c["id"] for c in cases}
    with pytest.raises(ValueError):
        build_cases(ROWS, lead_rule="guess")


def test_limit_and_no_leads():
    cases, _ = build_cases(ROWS, limit=1)
    assert len(cases) == 1
    cases, report = build_cases([r for r in ROWS if "(lead)" not in r["investors"]])
    assert cases == [] and report["cases"] == 0


# --- load_rows: cache only unless refresh, refresh capped ------------------------------------------------------

class Transport:
    """Stub Cala: counts requests, returns the rows."""

    def __init__(self, rows):
        self.rows, self.count = rows, 0

    def __call__(self, request):
        import httpx
        self.count += 1
        return httpx.Response(200, json={"results": self.rows, "entities": []})


def test_load_rows_cache_only_then_refresh_with_cap(tmp_path):
    import httpx
    stub = Transport(ROWS)
    client = httpx.Client(transport=httpx.MockTransport(stub))
    with pytest.raises(CaseError, match="--refresh"):
        load_rows(["q1"], tmp_path, http_client=client, api_key="k")
    assert stub.count == 0
    with pytest.raises(CaseError, match="--max-cala-calls"):
        load_rows(["q1", "q2"], tmp_path, http_client=client, api_key="k", refresh=True, max_cala_calls=1)
    assert stub.count == 0
    rows, ledger = load_rows(["q1"], tmp_path, http_client=client, api_key="k", refresh=True, max_cala_calls=1)
    assert len(rows) == len(ROWS) and ledger == {"cala_calls": 1, "cala_cache_hits": 0} and stub.count == 1
    rows, ledger = load_rows(["q1"], tmp_path, http_client=client, api_key="k")
    assert ledger == {"cala_calls": 0, "cala_cache_hits": 1} and stub.count == 1


# --- review fixes -----------------------------------------------------------------------------------------------

def test_non_latin_names_get_distinct_ids():
    from build_cases import slug
    assert slug("Proxima Fusion") == "proxima-fusion"
    assert slug("Ελληνικό Fund") != slug("Fund")
    assert slug("Фрукт") != slug("Пример")
    assert slug("Café Capital") == "cafe-capital"  # accents fold, no hash needed


def test_report_counts_the_whole_pull_even_with_a_limit():
    _, full = build_cases(ROWS)
    _, capped = build_cases(ROWS, limit=1)
    assert capped["cases"] == 1 and capped["eligible"] == full["eligible"] == 2
    for key in ("undisclosed", "no_date", "no_lead"):
        assert capped[key] == full[key]


def test_non_finite_amounts_are_unknown():
    assert parse_amount("nan", "€") is None and parse_amount("inf", "$") is None


def test_repeated_rows_make_one_case():
    cases, report = build_cases(ROWS + [dict(ROWS[2])])
    assert len(cases) == 2 and report["duplicates"] == 1


def test_a_subject_too_large_for_the_input_is_skipped_and_counted():
    huge = {**ROWS[2], "company": "P" * 30_000, "investors": "Otium (lead)"}
    cases, report = build_cases(ROWS + [huge])
    assert report["too_large"] == 1 and len(cases) == 2


def test_repeated_queries_are_fetched_once(tmp_path):
    import httpx
    stub = Transport(ROWS)
    client = httpx.Client(transport=httpx.MockTransport(stub))
    rows, ledger = load_rows(["q1", "q1"], tmp_path, http_client=client, api_key="k", refresh=True, max_cala_calls=1)
    assert stub.count == 1 and ledger == {"cala_calls": 1, "cala_cache_hits": 0} and len(rows) == len(ROWS)


# --- phase 9: leadline-profile cases from the same pull ---------------------------------------------------------

def test_profile_cases_one_per_company_with_known_fields():
    from build_cases import build_profile_cases
    cases, report = build_profile_cases(ROWS + [dict(ROWS[2], round_date="Jan 2024", stage="seed")])
    by_name = {c["input"]["user"]["name"]: c for c in cases}
    assert report["cases"] == len(cases) == len(by_name) == 8  # Proxima appears twice in the rows, once here
    proxima = by_name["Proxima Fusion"]
    assert proxima["input"]["user"] == {"id": "c_proxima-fusion", "kind": "startup", "name": "Proxima Fusion"}
    assert len(proxima["input"]["cala_facts"]) == 2
    want = proxima["expected"]["profile"]
    assert want["country"] == "Germany" and want["stage"] == "series-a"  # the latest dated row wins
    assert [s.casefold() for s in want["sectors"]] == ["fusion energy"]
    assert proxima["expected"]["changes"] == []


def test_profile_cases_validate_against_the_plugin():
    from build_cases import build_profile_cases
    plugin = load_plugin(PLUGINS / "leadline-profile")
    cases, _ = build_profile_cases(ROWS)
    for c in cases:
        plugin.validate_input(c["input"])
        plugin.validate_output(c["expected"])
        perfect = plugin.check(c["input"], c["expected"], c["expected"])
        assert perfect.total == pytest.approx(1.0), (c["id"], perfect.reasons)


def test_profile_cases_limit_and_unknown_rows():
    from build_cases import build_profile_cases
    cases, report = build_profile_cases(ROWS, limit=2)
    assert len(cases) == 2 and report["companies"] == 8
    none, report = build_profile_cases([{"company": "Ghost", "country": None, "sector": None, "stage": None}])
    assert none == [] and report["no_known_field"] == 1
