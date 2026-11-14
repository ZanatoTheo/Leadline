"""Cala rows -> time-split training cases for leadline-match.

No real users yet, so Cala history gives the answers: hide one funding round, ask "who will lead this startup's
round?" as of the day before it, and score against the lead the row names. Only rows that name a lead become cases
(`lead_rule="explicit"`: "Name (lead)"; `"explicit_or_sole"` also takes a row with a single named investor as its
lead, an assumption you opt into). Rows with no investors, no date or no lead are counted in the report and skipped.

Cala row shape (the cached bulk pull, 2026-11-14): {amount, company, country, currency, investors, round_date, sector,
stage}; `investors` is one comma-separated string with leads marked "(lead)"; amounts are in millions; `currency` is a
symbol; `round_date` is free text ("Jun 2025", "2025", "2025–2026").

Leak guard: the subject carries only what the startup itself knows (name, country, sectors, the stage and size it is
raising); candidates carry only rounds that ended on or before as_of, as dated facts. An investor's past rounds are
evidence, not its stated focus, so they never fill `stages`/`sectors` (the prefilter would drop on them).
Roster: every investor named anywhere in the pull is a candidate in every case, like a registered platform user,
whether or not it has history before as_of; most have none, so "no facts" does not point at the answer. The same
round returned twice (two queries) counts once.

`load_rows` reads the Cala pull from the app's disk cache (`app/data/cache`) and calls Cala only with
`refresh=True`, at most `max_cala_calls` times. Nothing else here touches the network.
"""
import calendar
import hashlib
import importlib.util
import math
import re
import sys
import unicodedata
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
NOT_DISCLOSED = {"", "not disclosed", "not stated", "undisclosed", "n/a", "na", "unknown", "none", "-"}
CURRENCIES = {"€": "EUR", "$": "USD", "£": "GBP", "¥": "JPY", "kr": "SEK", "chf": "CHF"}
MILLIONS_BELOW = 10_000  # Cala gives amounts in millions; a bigger number is taken as a full amount
LEAD_RULES = ("explicit", "explicit_or_sole")
MONTHS = {m.casefold(): i for i, m in enumerate(calendar.month_abbr) if m}
MONTHS.update({m.casefold(): i for i, m in enumerate(calendar.month_name) if m})


class CaseError(Exception):
    pass


def _load_prefilter():
    spec = importlib.util.spec_from_file_location("leadline_match_prefilter",
                                                  ROOT / "plugins" / "leadline-match" / "prefilter.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prefilter = _load_prefilter()


# --- parsing ---------------------------------------------------------------------------------------------------

def _blank(value) -> bool:
    return value is None or str(value).strip().casefold() in NOT_DISCLOSED


def slug(text: str) -> str:
    """Readable ASCII id; a name with letters that don't fold to ASCII (Greek, Cyrillic, ...) gets a short hash
    so two such names never share an id."""
    base = "".join(c for c in unicodedata.normalize("NFKD", str(text)) if not unicodedata.combining(c))
    ascii_text = base.encode("ascii", "ignore").decode()
    out = re.sub(r"[^a-z0-9]+", "-", ascii_text.casefold()).strip("-")
    if any(ord(c) > 127 and c.isalnum() for c in base) or not out:
        digest = hashlib.sha1(str(text).strip().casefold().encode()).hexdigest()[:8]
        out = f"{out}-{digest}" if out else digest
    return out


def parse_date(text):
    """Free-text round date -> (first day, last day) as ISO strings, or None."""
    if _blank(text):
        return None
    t = str(text).strip().replace("–", "-").replace("—", "-")
    if m := re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", t):
        try:
            d = date(*map(int, m.groups()))
        except ValueError:
            return None
        return d.isoformat(), d.isoformat()
    if m := re.fullmatch(r"([A-Za-z]+)\.?\s+(\d{4})", t):
        month = MONTHS.get(m.group(1).casefold())
        if month is None:
            return None
        year = int(m.group(2))
        return date(year, month, 1).isoformat(), date(year, month, calendar.monthrange(year, month)[1]).isoformat()
    if m := re.fullmatch(r"(\d{4})", t):
        return f"{m.group(1)}-01-01", f"{m.group(1)}-12-31"
    if m := re.fullmatch(r"(\d{4})\s*-\s*(\d{4})", t):
        a, b = sorted(m.groups())
        return f"{a}-01-01", f"{b}-12-31"
    return None


def parse_investors(text) -> list:
    """"A (lead), B" -> [{name, role}]; "Not disclosed" -> []."""
    if _blank(text):
        return []
    out = []
    for part in str(text).split(","):
        part = part.strip()
        lead = bool(re.search(r"\((co-)?lead\)", part, re.I))
        name = re.sub(r"\s*\((co-)?lead\)\s*", " ", part, flags=re.I).strip()
        if not _blank(name):
            out.append({"name": name, "role": "lead" if lead else "unknown"})
    return out


def parse_amount(amount, currency):
    """-> {amount, currency code} or None; no currency means unknown (never assumed)."""
    try:
        value = float(str(amount).replace(",", ""))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or value <= 0 or _blank(currency):
        return None
    code = CURRENCIES.get(str(currency).strip().casefold()) or CURRENCIES.get(str(currency).strip())
    if code is None:
        c = str(currency).strip()
        code = c.upper() if re.fullmatch(r"[A-Za-z]{3}", c) else None
    if code is None:
        return None
    return {"amount": value * 1_000_000 if value < MILLIONS_BELOW else value, "currency": code}


def _stage(text):
    return None if _blank(text) else "-".join(str(text).casefold().replace("_", " ").split())


def _sectors(text) -> list:
    if _blank(text):
        return []
    return [s.strip() for s in str(text).split("/") if not _blank(s)]


def parse_rows(rows) -> list:
    rounds = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or _blank(row.get("company")):
            continue
        rounds.append({
            "index": index, "company": str(row["company"]).strip(), "company_id": f"c_{slug(row['company'])}",
            "country": None if _blank(row.get("country")) else str(row["country"]).strip(),
            "sectors": _sectors(row.get("sector")), "stage": _stage(row.get("stage")),
            "date": parse_date(row.get("round_date")), "date_text": row.get("round_date"),
            "money": parse_amount(row.get("amount"), row.get("currency")),
            "investors": [{**x, "id": f"i_{slug(x['name'])}"} for x in parse_investors(row.get("investors"))],
        })
    return rounds


# --- cases -----------------------------------------------------------------------------------------------------

def _leads(r, lead_rule):
    leads = [x for x in r["investors"] if x["role"] == "lead"]
    if not leads and lead_rule == "explicit_or_sole" and len(r["investors"]) == 1:
        leads = r["investors"]
    return leads


def _label(start, end) -> str:
    if start == end:
        return start
    if start[:7] == end[:7]:
        return start[:7]
    if start[:4] == end[:4]:
        return start[:4]
    return f"{start[:4]}-{end[:4]}"


def _fact_id(r) -> str:
    return f"cala-{r['index']}"


def _subject(r) -> dict:
    return {"id": r["company_id"], "kind": "startup", "name": r["company"], "country": r["country"],
            "stage": r["stage"], "sectors": r["sectors"], "raising": r["money"],
            "facts": [{"id": _fact_id(r), "kind": "dataset", "ref": f"cala:row:{r['index']}"}]}


def _candidate(iid, name, rounds, as_of) -> dict:
    facts, last_lead = [], None
    for r in rounds:
        if not r["date"] or r["date"][1] > as_of:
            continue  # only rounds known to be over by as_of
        mine = next((x for x in r["investors"] if x["id"] == iid), None)
        if mine is None:
            continue
        verb = "Led" if mine["role"] == "lead" else "Invested in"
        about = ", ".join(x for x in (r["stage"], " / ".join(r["sectors"]), r["country"]) if x)
        facts.append({"id": _fact_id(r), "kind": "dataset", "ref": f"cala:row:{r['index']}", "date": r["date"][0],
                      "quote": f"{verb} {r['company']} ({about}), {r['date_text']}"})
        if mine["role"] == "lead" and (last_lead is None or r["date"][0] > last_lead):
            last_lead = r["date"][0]
    return {"id": iid, "kind": "investor", "name": name, "last_lead_date": last_lead, "facts": facts}


def _expected(r, leads) -> dict:
    fid = _fact_id(r)
    matches = [{"candidate_id": x["id"], "candidate_type": "investor", "rank": n, "score": 1.0, "score_parts": {},
                "role": "lead", "active": {"status": "active", "last_lead_date": r["date"][0]},
                "confidence": "high", "reasons": [{"text": f"led the {r['stage'] or ''} round of {r['company']}"
                                                           .replace("  ", " "), "evidence": [fid]}]}
               for n, x in enumerate(leads, 1)]
    return {"matches": matches, "rejected": [], "evidence": [{"id": fid, "kind": "dataset",
                                                             "ref": f"cala:row:{r['index']}"}], "warnings": []}


def build_cases(rows, lead_rule: str = "explicit", top_k: int = 10, limit: int | None = None,
                profile_store=None, profile_run=None, profile_key_tag=None):
    """-> (cases [{id, input, expected}], report). With `profile_store` and `profile_run` the subject profile is
    built by leadline-profile (phase 3 cache, key "<id>@<as_of>", plus "#<profile_key_tag>" when given, so profiles
    built under another profile strategy are not reused); otherwise it is taken from the row as is."""
    if lead_rule not in LEAD_RULES:
        raise ValueError(f"lead_rule must be one of {LEAD_RULES}, got {lead_rule!r}")
    rounds = parse_rows(rows)
    names = {}
    for r in rounds:
        for x in r["investors"]:
            names.setdefault(x["id"], x["name"])
    report = {"rows": len(rows), "rounds": len(rounds), "duplicates": 0, "undisclosed": 0, "no_date": 0,
              "no_lead": 0, "eligible": 0, "lead_dropped": 0, "too_large": 0, "cases": 0, "lead_rule": lead_rule}
    cases, seen_ids, seen_rounds = [], set(), set()
    for r in rounds:
        key = (r["company_id"], r["date_text"], r["stage"], tuple(x["id"] for x in r["investors"]))
        if key in seen_rounds:
            report["duplicates"] += 1
            continue
        seen_rounds.add(key)
        if not r["investors"]:
            report["undisclosed"] += 1
            continue
        if not r["date"]:
            report["no_date"] += 1
            continue
        leads = _leads(r, lead_rule)
        if not leads:
            report["no_lead"] += 1
            continue
        report["eligible"] += 1
        if limit is not None and len(cases) >= limit:
            continue  # keep counting the pull, but build (and pay for) no more cases
        as_of = (date.fromisoformat(r["date"][0]) - timedelta(days=1)).isoformat()
        subject = _subject(r)
        if profile_store is not None and profile_run is not None:
            subject = _built_subject(r, subject, as_of, profile_store, profile_run, profile_key_tag)
        candidates = [_candidate(iid, name, rounds, as_of) for iid, name in sorted(names.items())]
        request = {"direction": "startup_to_investors", "top_k": top_k, "as_of": as_of}
        try:
            filtered = prefilter.build_input(subject, candidates, request)
        except ValueError:
            report["too_large"] += 1  # the subject alone does not fit the input size cap
            continue
        kept = {c["id"] for c in (filtered["input"] or {}).get("candidates", [])}
        if not all(x["id"] in kept for x in leads):
            report["lead_dropped"] += 1  # the prefilter would lose this lead; phase 7's gate reports it
            continue
        case_id = f"{slug(r['company'])}-{_label(*r['date'])}"
        while case_id in seen_ids:
            case_id += "-b"
        seen_ids.add(case_id)
        cases.append({"id": case_id, "input": filtered["input"], "expected": _expected(r, leads)})
        report["cases"] += 1
    return cases, report


def build_profile_cases(rows, limit: int | None = None):
    """-> (leadline-profile cases, report). One case per company: input = the user (id, kind, name) and that
    company's raw Cala rows; expected = the profile those rows support (country, stage and sectors of the latest
    dated row, sectors of all rows), each field sourced to the rows. Companies with no known field are skipped."""
    rounds = parse_rows(rows)
    by_company = {}
    for r in rounds:
        by_company.setdefault(r["company_id"], []).append(r)
    report = {"rows": len(rows), "companies": len(by_company), "no_known_field": 0, "cases": 0}
    cases = []
    for company_id, group in by_company.items():
        latest = max(group, key=lambda r: (r["date"][1] if r["date"] else "", r["index"]))
        facts = [{"id": _fact_id(r), "kind": "dataset", "ref": f"cala:{company_id}:{r['index']}"} for r in group]
        fact_ids = [f["id"] for f in facts]
        sectors = list(dict.fromkeys(s for r in sorted(group, key=lambda r: r["index"]) for s in r["sectors"]))
        known = {"country": latest["country"], "stage": latest["stage"], "sectors": sectors or None}
        known = {k: v for k, v in known.items() if v}
        if not known:
            report["no_known_field"] += 1
            continue
        if limit is not None and len(cases) >= limit:
            continue
        name = latest["company"]
        profile = {"id": company_id, "kind": "startup", "name": name, **known, "facts": facts,
                   "sources": {k: {"facts": fact_ids} for k in known}}
        completeness = round(len(known) / 3, 4)
        cases.append({"id": f"profile-{slug(name)}",
                      "input": {"user": {"id": company_id, "kind": "startup", "name": name},
                                "cala_facts": [rows[r["index"]] for r in group]},
                      "expected": {"profile": profile,
                                   "rating": {"total": completeness, "parts": {"completeness": completeness},
                                              "sources": fact_ids},
                                   "changes": []}})
        report["cases"] += 1
    return cases, report


def _built_subject(r, subject, as_of, store, run, tag=None):
    from profiles import get_or_build, profile_key
    user = {"id": subject["id"], "kind": "startup", "name": subject["name"],
            "fields": {k: subject[k] for k in ("country", "stage", "sectors") if subject.get(k)}}
    fact = {"company": r["company"], "country": r["country"], "sector": " / ".join(r["sectors"]),
            "stage": r["stage"]}  # the row without its investors: they are the answer
    key = profile_key(user["id"], as_of) + (f"#{tag}" if tag else "")
    built = get_or_build(store, user, run, cala_facts=[fact], as_of=as_of, key=key)["profile"]
    return {**built, "raising": r["money"]}


# --- the Cala pull ---------------------------------------------------------------------------------------------

class _NoNetwork:
    """An http client that refuses every request: without --refresh, Cala is read from the cache only."""

    def request(self, method, url, **kwargs):
        raise CaseError(f"blocked a Cala request ({method} {url}): run with --refresh to call Cala")


def _cala_client(cache_dir, http_client, api_key):
    sys.path.insert(0, str(REPO / "app"))
    from ingest.cala_client import CalaClient
    return CalaClient(api_key=api_key, cache_dir=cache_dir, http_client=http_client)


def load_rows(queries, cache_dir, refresh: bool = False, max_cala_calls: int = 5, http_client=None, api_key=None):
    """-> (rows, ledger {cala_calls, cala_cache_hits}). Cala is called only for uncached queries, only with
    `refresh`, and never more than `max_cala_calls` times (checked before the first call)."""
    queries = list(dict.fromkeys(queries))  # a repeated query is one cache entry and one call
    client = _cala_client(cache_dir, http_client if refresh else _NoNetwork(), api_key)
    url = f"{client.base_url}/v1/knowledge/query"
    misses = [q for q in queries
              if not client._cache_path("POST", url, None, {"input": q, "return_entities": True}).exists()]
    if misses and not refresh:
        raise CaseError(f"{len(misses)} of {len(queries)} Cala queries are not cached in {cache_dir}; run with "
                        f"--refresh (spends {len(misses)} Cala call(s), about {len(misses) + 1} credits)")
    if len(misses) > max_cala_calls:
        raise CaseError(f"--refresh needs {len(misses)} Cala calls, more than --max-cala-calls {max_cala_calls}; "
                        "raise the cap or use fewer queries")
    rows = []
    for q in queries:
        data = client.knowledge_query(q)
        rows += [r for r in data.get("results") or [] if isinstance(r, dict)]
    return rows, {"cala_calls": len(misses), "cala_cache_hits": len(queries) - len(misses)}
