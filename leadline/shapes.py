"""The Python side of the frontend contract: DB rows -> the frontend's exact types, and frontend records ->
`leadline-profile` inputs. Pure functions, no I/O.

The types are frontend/src/lib/{leadline/types.ts, leadline/match-types.ts, server/db.ts, cala/client.ts}; their JSON
Schemas are generated into contracts/schemas/ by scripts/gen_contract_schemas.sh, and tests/test_shapes.py checks every
function here against them. The schemas are strict (no extra keys, text fields never null), which raw `LeadlineDb`
rows are not: they carry `provenance` and NULLs.
"""
from __future__ import annotations

import calendar
import re
import unicodedata
from datetime import date

MAX_CALA_FACTS = 100  # leadline-profile input.schema.json: cala_facts maxItems


# --- keys ---------------------------------------------------------------------------------------------------------

def slugify(name: str) -> str:
    """types.ts `slugify`: lower case, NFKD, strip combining accents (U+0300-U+036F), non [a-z0-9] runs -> "-", no
    leading/trailing "-"."""
    text = unicodedata.normalize("NFKD", (name or "").lower())
    text = re.sub("[̀-ͯ]", "", text)
    return re.sub("[^a-z0-9]+", "-", text).strip("-")


def profile_key_founder(founder_id: str) -> str:
    return f"founder:{founder_id}"


def profile_key_investor(name: str) -> str:
    return f"investor:{slugify(name)}"


# --- DB rows -> frontend types --------------------------------------------------------------------------------------

def _text(value) -> str:
    return "" if value is None else str(value)


def _sources(sources) -> list:
    return [{"publisher": _text(s.get("publisher")), "title": _text(s.get("title")), "url": s["url"]}
            for s in sources or [] if isinstance(s, dict) and s.get("url")]


def deal_out(row: dict) -> dict:
    """`LeadlineDb.rounds()` row -> `Deal` (types.ts). Missing text -> "", provenance and country dropped."""
    deal = {"id": row["id"], "company": row["company"], "companyDescription": _text(row.get("companyDescription")),
            "industry": _text(row.get("industry")), "round": _text(row.get("round")),
            "amountEurM": row.get("amountEurM"), "announced": row["announced"],
            "leadInvestors": list(row.get("leadInvestors") or []),
            "otherInvestors": list(row.get("otherInvestors") or []), "sources": _sources(row.get("sources"))}
    if row.get("calaEntityId"):
        deal["calaEntityId"] = row["calaEntityId"]
    return deal


def fund_close_out(row: dict) -> dict | None:
    """`LeadlineDb.fund_closes()` row -> `FundClose`, or None without a close date (timing math needs one)."""
    if not row.get("closed"):
        return None
    return {"investor": row["investor"], "fundName": _text(row.get("fundName")), "sizeEurM": row.get("sizeEurM"),
            "closed": row["closed"], "sources": _sources(row.get("sources"))}


def entity_out(row: dict) -> dict:
    """`LeadlineDb.entity()` row -> `CalaEntity` (cala/client.ts)."""
    return {"id": row["id"], "name": _text(row.get("name")), "entity_type": _text(row.get("entity_type"))}


def user_out(row: dict) -> dict:
    """`LeadlineDb` user row -> `User` (server/db.ts): optional ids only when set; `isDemo` is internal.
    `User` requires `passwordHash` (the TS server verifies logins with it), so this carries the scrypt hash: send it
    only to the TS server, never to a browser (the TS side's `toSessionUser` is what reaches the browser)."""
    user = {k: row[k] for k in ("id", "role", "name", "email", "passwordHash", "createdAt")}
    user["passwordHash"] = _text(user["passwordHash"])
    for key in ("founderId", "investorName"):
        if row.get(key):
            user[key] = row[key]
    return user


def founder_record_out(row: dict) -> dict:
    """`LeadlineDb` founder row -> `FounderRecord` (match-types.ts)."""
    return {"id": row["id"], "profile": row["profile"], "founderName": _text(row.get("founderName")),
            "email": _text(row.get("email")), "discoverable": bool(row.get("discoverable")),
            "updatedAt": row["updatedAt"]}


def public_founder_out(row: dict) -> dict:
    """-> `PublicFounder`: what an investor sees, no contact details."""
    return {"id": row["id"], "profile": row["profile"], "founderName": _text(row.get("founderName"))}


def intro_out(row: dict) -> dict:
    """`LeadlineDb` intro row -> `Intro` (match-types.ts)."""
    intro = {k: row[k] for k in ("id", "founderId", "investor", "direction", "status", "createdAt")}
    intro["note"] = _text(row.get("note"))
    for key in ("passReason", "respondedAt"):
        if row.get(key):
            intro[key] = row[key]
    return intro


# --- frontend records -> leadline-profile input ----------------------------------------------------------------------

def _round_date(deal: dict) -> str:
    """The date as Cala reported it. db.deal_from_row fills a month-only date with the 15th and a year-only date with
    1 July, and gives such rounds the id "company:date:round" (an exact date's id is "company:date"), so the id says
    which one it was; "Jun 2023" / "2023" then parse back to the same id."""
    announced = deal["announced"]
    if deal.get("id", "").lower() == f"{deal['company']}:{announced}".lower():
        return announced
    year, month, day = announced.split("-")
    if month == "07" and day == "01":
        return year
    if day == "15":
        return f"{calendar.month_abbr[int(month)]} {year}"
    return announced


def _amount(value: float) -> str:
    """EUR millions with an explicit unit, so db's "bare numbers below 10,000 are millions" rule never applies; 4
    decimals is the precision the DB stores."""
    return f"€{value:.4f}".rstrip("0").rstrip(".") + "M"


def _name(name: str) -> str:
    return " ".join(str(name).replace(",", " ").split())  # parse_investors splits on commas


def deal_to_cala_row(deal: dict) -> dict:
    """A stored round (a `LeadlineDb.rounds()` row) back into the Cala pull's row shape, the shape `leadline-profile`
    was trained on: {company, country, sector, stage, round_date, amount, investors "A (lead), B"}. `country` is sent
    when the DB row has one. db.deal_from_row parses the row back to the same id, date and amount."""
    leads = [f"{_name(n)} (lead)" for n in deal.get("leadInvestors") or []]
    others = [_name(n) for n in deal.get("otherInvestors") or []]
    row = {"company": deal["company"], "sector": _text(deal.get("industry")) or None,
           "stage": _text(deal.get("round")) or None, "round_date": _round_date(deal),
           "investors": ", ".join(leads + others) or "Not disclosed"}
    if deal.get("amountEurM") is not None:
        row["amount"] = _amount(deal["amountEurM"])
    if deal.get("country"):
        row["country"] = deal["country"]
    return {k: v for k, v in row.items() if v is not None}


def _profile_input(user: dict, rounds, as_of) -> dict:
    return {"user": user, "cala_facts": [deal_to_cala_row(d) for d in list(rounds or [])[:MAX_CALA_FACTS]],
            "as_of": as_of or date.today().isoformat()}


def founder_profile_input(record: dict, rounds=(), as_of: str | None = None) -> dict:
    """`FounderRecord` -> leadline-profile input: the founder's own answers as `fields`, the company's stored rounds
    as `cala_facts`."""
    profile = dict(record.get("profile") or {})
    name = profile.pop("startupName", None) or _text(record.get("founderName"))
    user = {"id": profile_key_founder(record["id"]), "kind": "startup", "name": name, "website": None,
            "fields": profile}
    return _profile_input(user, rounds, as_of)


def investor_profile_input(name: str, rounds=(), as_of: str | None = None) -> dict:
    """An investor (fund) name -> leadline-profile input with the rounds it appears in as `cala_facts`."""
    user = {"id": profile_key_investor(name), "kind": "investor", "name": name, "website": None, "fields": {}}
    return _profile_input(user, rounds, as_of)
