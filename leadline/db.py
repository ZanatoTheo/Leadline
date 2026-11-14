"""Leadline's one SQLite database (WAL), shaped like the frontend's data so its routes can move onto it (phase 10).

Shapes follow frontend/src/lib/leadline/types.ts, match-types.ts and lib/server/db.ts. Reads return the frontend's
camelCase objects; columns are snake_case; lists and objects are JSON text.

- Sourced data: `entities`, `funding_rounds` (the frontend's `Deal`; id = "company:announced" lowercased),
  `fund_closes`, `evidence_sources` (`Source`, attached to any row). Each row has provenance: provider
  (cala | context_dev | simulated | user), source_url, trace_id, fetched_at. provider "simulated" = made-up data.
- Computed snapshots, one table per frontend feature (SNAPSHOT_TABLES): the payload as the frontend type, its mode
  (live | simulated), and `synthetic_fields`: the heuristic fields in it (scores, headlines, templates), from
  SYNTHETIC_FIELDS. A simulated snapshot is wholly made up (["*"]).
- Agent profiles: `LeadlineDb` is a `ProfileStore`, so `profiles.get_or_build` / `update_profile` use the same file
  (table `profiles`, also readable as the view `agent_profiles`).
- App data from server/db.ts: `users`, `sessions`, `founders`, `intros`, with the same rules (pending intros are
  not duplicated; only the recipient answers). Demo users have is_demo = 1.

`record_cala(kind, request, reply)` stores what a Cala tool returned (rounds, entities, sources); `cala_hook()` gives
it to `venus.cala.Cala(on_result=...)`.
"""
import hashlib
import json
import re
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from build_cases import parse_amount, parse_date, parse_investors
from profiles import ProfileStore, _record

SCHEMA_VERSION = 2  # v2: funding_rounds.country, jobs, rankings (additive; v1 files migrate on open)
PROVIDERS = ("cala", "context_dev", "simulated", "user")
MODES = ("live", "simulated")
EUR_PER = {"EUR": 1.0, "USD": 0.92, "GBP": 1.17}  # the frontend's rates (normalize.ts)

SNAPSHOT_TABLES = {
    "shortlist": "shortlist_runs",  # ShortlistResponse
    "twins": "twins_reports",  # TwinsResponse
    "investor_brief": "investor_briefs",  # InvestorBrief
    "thesis": "investor_theses",  # InvestorThesis
    "fit": "fit_reports",  # FitReport
    "signals": "signals",  # Signal[]
    "diligence": "diligence_reports",  # StartupDiligence | CompanyDiligence
    "outreach": "outreach_drafts",  # OutreachDraft
}
SYNTHETIC_FIELDS = {  # heuristic or templated fields: computed by Leadline, not facts from a source
    "shortlist": ["investors[].score", "investors[].explanation", "investors[].conflict",
                  "investors[].timingStatus", "investors[].timingHeadline"],
    "twins": ["twins[].sharedTerms", "monthsToNext", "reachedNext"],
    "investor_brief": ["investor.score", "investor.explanation", "investor.conflict", "timing", "synergies"],
    "thesis": ["timing", "breakouts"],
    "fit": ["score", "headline", "points", "conflict", "timing", "synergies", "stage.raiseFits"],
    "signals": ["[].conflict", "[].synergyCount"],
    "diligence": ["fit", "points"],
    "outreach": ["subject", "body"],
}

PROVENANCE = """provider TEXT NOT NULL CHECK (provider IN ('cala', 'context_dev', 'simulated', 'user')),
    source_url TEXT, trace_id TEXT, fetched_at TEXT NOT NULL"""
TABLES = [
    f"""CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY, name TEXT, entity_type TEXT, description TEXT, {PROVENANCE})""",
    f"""CREATE TABLE IF NOT EXISTS funding_rounds (
    id TEXT PRIMARY KEY, company TEXT NOT NULL, company_description TEXT, industry TEXT, round TEXT,
    amount_eur_m REAL, announced TEXT NOT NULL, lead_investors TEXT NOT NULL DEFAULT '[]',
    other_investors TEXT NOT NULL DEFAULT '[]', cala_entity_id TEXT, {PROVENANCE}, country TEXT)""",
    "CREATE INDEX IF NOT EXISTS funding_rounds_company ON funding_rounds (company COLLATE NOCASE)",
    "CREATE INDEX IF NOT EXISTS funding_rounds_announced ON funding_rounds (announced)",
    f"""CREATE TABLE IF NOT EXISTS fund_closes (
    id TEXT PRIMARY KEY, investor TEXT NOT NULL, fund_name TEXT, size_eur_m REAL, closed TEXT, {PROVENANCE})""",
    """CREATE TABLE IF NOT EXISTS evidence_sources (
    id INTEGER PRIMARY KEY, owner_table TEXT NOT NULL, owner_id TEXT NOT NULL, publisher TEXT, title TEXT,
    url TEXT NOT NULL, provider TEXT NOT NULL, trace_id TEXT, fetched_at TEXT NOT NULL,
    UNIQUE (owner_table, owner_id, url))""",
    """CREATE TABLE IF NOT EXISTS founders (
    id TEXT PRIMARY KEY, profile TEXT NOT NULL, founder_name TEXT, email TEXT, discoverable INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY, role TEXT NOT NULL CHECK (role IN ('founder', 'investor')), name TEXT,
    email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL DEFAULT '', founder_id TEXT REFERENCES founders (id),
    investor_name TEXT, created_at TEXT NOT NULL, is_demo INTEGER NOT NULL DEFAULT 0)""",
    """CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users (id) ON DELETE CASCADE, expires_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS intros (
    id TEXT PRIMARY KEY, founder_id TEXT NOT NULL REFERENCES founders (id), investor TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('founder-to-investor', 'investor-to-founder')), note TEXT,
    status TEXT NOT NULL CHECK (status IN ('pending', 'accepted', 'passed')), pass_reason TEXT,
    created_at TEXT NOT NULL, responded_at TEXT)""",
    "CREATE VIEW IF NOT EXISTS agent_profiles AS SELECT * FROM profiles",
    # background work for the service (phase 5-6): one row per profile build or rank run
    """CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK (kind IN ('profile', 'rank')), subject_key TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'done', 'failed')), attempts INTEGER NOT NULL DEFAULT 0,
    error TEXT, trace_id TEXT, created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT)""",
    "CREATE INDEX IF NOT EXISTS jobs_status ON jobs (status, created_at)",
    "CREATE INDEX IF NOT EXISTS jobs_subject ON jobs (kind, subject_key, created_at)",
    # a user's ranking: the candidates (keys + profile versions) it was computed from and the agent's answer
    """CREATE TABLE IF NOT EXISTS rankings (
    id TEXT PRIMARY KEY, subject_key TEXT NOT NULL, subject_version INTEGER, candidates TEXT NOT NULL,
    payload TEXT NOT NULL, trace_id TEXT, created_at TEXT NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS rankings_subject ON rankings (subject_key, created_at)",
] + [f"""CREATE TABLE IF NOT EXISTS {table} (
    id TEXT PRIMARY KEY, key TEXT NOT NULL, mode TEXT NOT NULL CHECK (mode IN ('live', 'simulated')),
    payload TEXT NOT NULL, synthetic_fields TEXT NOT NULL, trace_id TEXT, created_at TEXT NOT NULL)"""
     for table in SNAPSHOT_TABLES.values()] + [
    f"CREATE INDEX IF NOT EXISTS {table}_key ON {table} (key, created_at)" for table in SNAPSHOT_TABLES.values()]
JOB_KINDS = ("profile", "rank")
PROFILE_PREFIX = {"startup": "founder:", "investor": "investor:"}  # profile keys of real users, by kind


class DbError(Exception):
    pass


def _utc_iso(text: str) -> str:
    """Any ISO date-time ("...Z", "... 12:00:00", "+02:00") -> UTC isoformat, so expiry compares as text with
    _now(). A time without a zone is taken as UTC."""
    try:
        when = datetime.fromisoformat(str(text).strip().replace("Z", "+00:00"))
    except ValueError:
        raise DbError(f"not an ISO date-time: {text!r}") from None
    when = when.replace(tzinfo=timezone.utc) if when.tzinfo is None else when.astimezone(timezone.utc)
    return when.isoformat()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _provider(provider):
    if provider not in PROVIDERS:
        raise DbError(f"provider must be one of {PROVIDERS}, got {provider!r}")
    return provider


# --- Cala rows -> Deal --------------------------------------------------------------------------------------------

def _blank(v) -> bool:
    return v is None or (isinstance(v, str) and v.strip().casefold() in ("", "n/a", "none", "null", "unknown",
                                                                          "not disclosed", "undisclosed"))


def _announced(text):
    """Free-text date -> (one ISO day, exact?), filled like the frontend: month only -> the 15th, year only ->
    1 July. (None, False) when there is no single date."""
    span = parse_date(text)
    if span is None:
        return None, False
    start, end = span
    if start == end:
        return start, True
    if start[:7] == end[:7]:
        return start[:7] + "-15", False
    if start[:4] == end[:4]:
        return start[:4] + "-07-01", False
    return None, False  # a range of years: no single date


AMOUNT_RE = re.compile(r"^\s*(€|\$|£|EUR|USD|GBP)?\s*([\d.,]+)\s*(k|m|b|bn|million|billion|thousand)?\s*"
                       r"(EUR|USD|GBP|€|\$|£)?\s*$", re.I)
SYMBOLS = {"€": "EUR", "$": "USD", "£": "GBP"}
SCALE = {"k": 1e-3, "thousand": 1e-3, "m": 1.0, "million": 1.0, "b": 1e3, "bn": 1e3, "billion": 1e3}


def _amount_eur_m(amount, currency=None):
    """EUR millions, or None when the amount or currency is unknown (a currency is never assumed)."""
    if _blank(amount):
        return None
    if not _blank(currency):
        money = parse_amount(amount, currency)
        if money is None:
            return None
        rate = EUR_PER.get(money["currency"])
        return round(money["amount"] / 1e6 * rate, 4) if rate else None
    if isinstance(amount, (int, float)):
        return None
    m = AMOUNT_RE.match(str(amount))
    if not m:
        return None
    code = m.group(1) or m.group(4)
    code = SYMBOLS.get(code, (code or "").upper())
    try:
        value = float(m.group(2).replace(",", ""))
    except ValueError:
        return None
    scale = SCALE.get((m.group(3) or "").lower())
    if scale is None:
        scale = 1.0 if value < 10_000 else 1e-6  # bare numbers: millions below 10,000 (build_cases convention)
    rate = EUR_PER.get(code)
    return round(value * scale * rate, 4) if rate and value > 0 else None


def _names(value) -> list:
    if _blank(value):
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if not _blank(v)]
    return [x["name"] for x in parse_investors(value)]


def _first(row, *keys):
    for k in keys:
        if not _blank(row.get(k)):
            return str(row[k]).strip() if not isinstance(row[k], (list, dict)) else row[k]
    return None


def _country(value) -> str | None:
    """A country as text: Cala may send a list (the first name counts) or an object with a name."""
    if isinstance(value, dict):
        value = value.get("name")
    elif isinstance(value, (list, tuple)):
        value = next((v.get("name") if isinstance(v, dict) else v for v in value if not _blank(v)), None)
    return None if _blank(value) or isinstance(value, (list, dict)) else str(value).strip()


def _slug(text: str) -> str:
    """"Series A" / "series-a" / "SERIES_A" -> "series-a": round names compared this way."""
    return re.sub(r"[^a-z0-9]+", "-", str(text).casefold()).strip("-")


def deal_id(company: str, announced: str) -> str:
    return f"{company}:{announced}".lower()


def deal_from_row(row) -> dict | None:
    """A Cala knowledge-query row (frontend columns or the ingest pull's columns) -> a Deal, or None without a
    company or a single date."""
    if not isinstance(row, dict):
        return None
    company = _first(row, "company", "company_name", "name")
    announced, exact = _announced(_first(row, "announced_date", "round_date", "date", "announced"))
    if not company or not announced:
        return None
    round_name = _first(row, "round_type", "round", "stage")
    if any(k in row for k in ("lead_investors", "other_investors")):
        leads, others = _names(row.get("lead_investors")), _names(row.get("other_investors"))
    else:
        parsed = parse_investors(row.get("investors")) if not _blank(row.get("investors")) else []
        leads = [x["name"] for x in parsed if x["role"] == "lead"]
        others = [x["name"] for x in parsed if x["role"] != "lead"]
    # The frontend's Deal.id is "company:announced". A filled-in date (month or year only) is shared by every round
    # of that company in the period, so the round name is added to keep them apart.
    rid = deal_id(company, announced) if exact else f"{deal_id(company, announced)}:{(round_name or '').lower()}"
    return {"id": rid, "company": company,
            "companyDescription": _first(row, "company_description", "description"),
            "industry": _first(row, "industry", "sector"), "round": round_name,
            "amountEurM": _amount_eur_m(row.get("amount"), row.get("currency")), "announced": announced,
            "leadInvestors": leads, "otherInvestors": others, "sources": [], "country": _country(row.get("country"))}


def _origin_source(origin) -> dict | None:
    origin = origin if isinstance(origin, dict) else {}
    src = origin.get("source") if isinstance(origin.get("source"), dict) else {}
    doc = origin.get("document") if isinstance(origin.get("document"), dict) else {}
    url = doc.get("url") or src.get("url")
    if not url:
        return None
    return {"publisher": src.get("name") or "", "title": doc.get("name") or "", "url": url}


# --- the database -------------------------------------------------------------------------------------------------

class LeadlineDb(ProfileStore):
    def __init__(self, path):
        from pathlib import Path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(path, timeout=30)
        try:
            con.execute("PRAGMA journal_mode=WAL")  # readers never block the writer; must be set outside a transaction
        finally:
            con.close()
        super().__init__(path)  # the profiles table
        with self._connect() as db:
            for statement in TABLES:
                db.execute(statement)
            # v1 -> v2: CREATE TABLE IF NOT EXISTS leaves an old funding_rounds as it was; add the column it lacks.
            if "country" not in {r["name"] for r in db.execute("PRAGMA table_info(funding_rounds)")}:
                db.execute("ALTER TABLE funding_rounds ADD COLUMN country TEXT")
            if db.execute("PRAGMA user_version").fetchone()[0] < SCHEMA_VERSION:
                db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    timeout = 30  # seconds a write waits for another writer

    @contextmanager
    def _connect(self, write: bool = True):
        """One transaction. Writes take the write lock at once (BEGIN IMMEDIATE), so read-then-write steps such as
        claim_job can't interleave; reads (`write=False`) use a plain BEGIN and, with WAL, never wait for a writer."""
        db = sqlite3.connect(self.path, timeout=self.timeout, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys = ON")
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield db
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    # -- sourced data ------------------------------------------------------------------------------------------

    def upsert_round(self, deal: dict, provider: str, source_url=None, trace_id=None, fetched_at=None) -> str:
        _provider(provider)
        if not deal.get("company") or not deal.get("announced"):
            raise DbError("a round needs company and announced")
        rid = deal.get("id") or deal_id(deal["company"], deal["announced"])
        with self._connect() as db:
            if not self._gate_provenance(db, "funding_rounds", rid, provider):
                return rid
            db.execute(
                """INSERT INTO funding_rounds (id, company, company_description, industry, round, amount_eur_m,
                  announced, lead_investors, other_investors, cala_entity_id, provider, source_url, trace_id,
                  fetched_at, country) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (id) DO UPDATE SET
                  country = COALESCE(excluded.country, country),
                  company_description = COALESCE(excluded.company_description, company_description),
                  industry = COALESCE(excluded.industry, industry), round = COALESCE(excluded.round, round),
                  amount_eur_m = COALESCE(excluded.amount_eur_m, amount_eur_m),
                  lead_investors = CASE WHEN excluded.lead_investors = '[]' THEN lead_investors
                                        ELSE excluded.lead_investors END,
                  other_investors = CASE WHEN excluded.other_investors = '[]' THEN other_investors
                                         ELSE excluded.other_investors END,
                  cala_entity_id = COALESCE(excluded.cala_entity_id, cala_entity_id),
                  provider = excluded.provider, source_url = COALESCE(excluded.source_url, source_url),
                  trace_id = COALESCE(excluded.trace_id, trace_id), fetched_at = excluded.fetched_at""",
                (rid, deal["company"], deal.get("companyDescription"), deal.get("industry"), deal.get("round"),
                 deal.get("amountEurM"), deal["announced"], json.dumps(list(deal.get("leadInvestors") or [])),
                 json.dumps(list(deal.get("otherInvestors") or [])), deal.get("calaEntityId"), provider,
                 source_url, trace_id, fetched_at or _now(), _country(deal.get("country"))))
            self._add_sources(db, "funding_rounds", rid, deal.get("sources") or [], provider, trace_id)
        return rid

    def upsert_fund_close(self, close: dict, provider: str, source_url=None, trace_id=None, fetched_at=None) -> str:
        _provider(provider)
        if not close.get("investor"):
            raise DbError("a fund close needs an investor")
        cid = f"{close['investor']}:{close.get('fundName') or ''}:{close.get('closed') or ''}".lower()
        with self._connect() as db:
            if not self._gate_provenance(db, "fund_closes", cid, provider):
                return cid
            db.execute("""INSERT INTO fund_closes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (id) DO UPDATE SET size_eur_m = COALESCE(excluded.size_eur_m, size_eur_m),
                  provider = excluded.provider, source_url = COALESCE(excluded.source_url, source_url),
                  trace_id = COALESCE(excluded.trace_id, trace_id), fetched_at = excluded.fetched_at""",
                       (cid, close["investor"], close.get("fundName"), close.get("sizeEurM"), close.get("closed"),
                        provider, source_url, trace_id, fetched_at or _now()))
            self._add_sources(db, "fund_closes", cid, close.get("sources") or [], provider, trace_id)
        return cid

    def upsert_entity(self, entity: dict, provider: str, source_url=None, trace_id=None, fetched_at=None) -> str:
        _provider(provider)
        if not entity.get("id"):
            raise DbError("an entity needs an id")
        with self._connect() as db:
            if not self._gate_provenance(db, "entities", entity["id"], provider):
                return entity["id"]
            db.execute("""INSERT INTO entities VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (id) DO UPDATE SET name = COALESCE(excluded.name, name),
                  entity_type = COALESCE(excluded.entity_type, entity_type),
                  description = COALESCE(excluded.description, description), provider = excluded.provider,
                  source_url = COALESCE(excluded.source_url, source_url),
                  trace_id = COALESCE(excluded.trace_id, trace_id), fetched_at = excluded.fetched_at""",
                       (entity["id"], entity.get("name"), entity.get("entity_type"), entity.get("description"),
                        provider, source_url, trace_id, fetched_at or _now()))
        return entity["id"]

    @staticmethod
    def _gate_provenance(db, table, row_id, provider) -> bool:
        """Simulated data never overwrites real data (-> False: skip the write), and real data replaces a simulated
        row whole (its sources too), so no made-up value survives under a real label. Same-kind writes merge."""
        old = db.execute(f"SELECT provider FROM {table} WHERE id = ?", (row_id,)).fetchone()
        if old is None:
            return True
        if provider == "simulated" and old["provider"] != "simulated":
            return False
        if old["provider"] == "simulated" and provider != "simulated":
            db.execute(f"DELETE FROM {table} WHERE id = ?", (row_id,))
            db.execute("DELETE FROM evidence_sources WHERE owner_table = ? AND owner_id = ?", (table, row_id))
        return True

    @staticmethod
    def _add_sources(db, owner_table, owner_id, sources, provider, trace_id) -> int:
        added = 0
        for s in sources:
            if not isinstance(s, dict) or not s.get("url"):
                continue
            cur = db.execute("""INSERT OR IGNORE INTO evidence_sources
                (owner_table, owner_id, publisher, title, url, provider, trace_id, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", (owner_table, owner_id, s.get("publisher") or "",
                                                     s.get("title") or "", s["url"], provider, trace_id, _now()))
            added += cur.rowcount
        return added

    def add_sources(self, owner_table: str, owner_id: str, sources: list, provider: str = "cala",
                    trace_id=None) -> int:
        _provider(provider)
        with self._connect() as db:
            return self._add_sources(db, owner_table, owner_id, sources, provider, trace_id)

    @staticmethod
    def _sources(db, owner_table, owner_id) -> list:
        rows = db.execute("SELECT publisher, title, url FROM evidence_sources WHERE owner_table = ? AND owner_id = ? "
                          "ORDER BY id", (owner_table, owner_id)).fetchall()
        return [{"publisher": r["publisher"], "title": r["title"], "url": r["url"]} for r in rows]

    @staticmethod
    def _provenance(r) -> dict:
        return {"provider": r["provider"], "sourceUrl": r["source_url"], "traceId": r["trace_id"],
                "fetchedAt": r["fetched_at"], "synthetic": r["provider"] == "simulated"}

    def rounds(self, company=None, investor=None, since=None, limit: int | None = None, *, industry_terms=None,
               stages=None, countries=None) -> list:
        """Deals, newest first. `investor` matches a lead or other investor, ignoring case. `industry_terms`: any term
        inside the industry text; `stages`: round names compared as slugs ("Series A" == "series-a"); `countries`:
        country names, ignoring case. Rows without the field never match its filter."""
        sql, args = "SELECT * FROM funding_rounds WHERE 1 = 1", []
        if company:
            sql += " AND company = ? COLLATE NOCASE"
            args.append(company)
        if investor:
            sql += (" AND (EXISTS (SELECT 1 FROM json_each(lead_investors) WHERE lower(value) = lower(?))"
                    " OR EXISTS (SELECT 1 FROM json_each(other_investors) WHERE lower(value) = lower(?)))")
            args += [investor, investor]
        if since:
            sql += " AND announced >= ?"
            args.append(since)
        sql += " ORDER BY announced DESC, id"
        terms = [t.strip().casefold() for t in industry_terms or [] if t and t.strip()]
        stage_slugs = {_slug(s) for s in stages or [] if s and _slug(s)}  # a blank or "-" stage is no filter
        country_names = {c.strip().casefold() for c in countries or [] if c and c.strip()}

        def keep(r) -> bool:
            if terms and not any(t in (r["industry"] or "").casefold() for t in terms):
                return False
            if stage_slugs and _slug(r["round"] or "") not in stage_slugs:
                return False
            return not country_names or (r["country"] or "").casefold() in country_names

        with self._connect(write=False) as db:
            rows = [r for r in db.execute(sql, args).fetchall() if keep(r)]
            rows = rows[:int(limit)] if limit else rows
            return [{"id": r["id"], "company": r["company"], "companyDescription": r["company_description"],
                     "industry": r["industry"], "round": r["round"], "amountEurM": r["amount_eur_m"],
                     "announced": r["announced"], "leadInvestors": json.loads(r["lead_investors"]),
                     "otherInvestors": json.loads(r["other_investors"]),
                     "sources": self._sources(db, "funding_rounds", r["id"]), "calaEntityId": r["cala_entity_id"],
                     "country": r["country"], "provenance": self._provenance(r)} for r in rows]

    def fund_closes(self, investor=None) -> list:
        sql, args = "SELECT * FROM fund_closes", []
        if investor:
            sql += " WHERE investor = ? COLLATE NOCASE"
            args.append(investor)
        with self._connect(write=False) as db:
            return [{"investor": r["investor"], "fundName": r["fund_name"], "sizeEurM": r["size_eur_m"],
                     "closed": r["closed"], "sources": self._sources(db, "fund_closes", r["id"]),
                     "provenance": self._provenance(r)}
                    for r in db.execute(sql + " ORDER BY closed DESC", args).fetchall()]

    def entity(self, entity_id: str) -> dict | None:
        with self._connect(write=False) as db:
            r = db.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
        if r is None:
            return None
        return {"id": r["id"], "name": r["name"], "entity_type": r["entity_type"], "description": r["description"],
                "provenance": self._provenance(r)}

    # -- Cala results --------------------------------------------------------------------------------------------

    def record_cala(self, kind: str, request, reply, trace_id=None, provider: str = "cala") -> dict:
        """Store a Cala reply: query rows -> funding_rounds, entities -> entities, search origins -> evidence_sources
        on the rounds whose company the claim names. Returns counts of what was written."""
        counts = {"rounds": 0, "entities": 0, "sources": 0}
        if not isinstance(reply, dict):
            return counts
        if kind == "knowledge_query":
            for row in reply.get("results") or []:
                deal = deal_from_row(row)
                if deal:
                    self.upsert_round(deal, provider, trace_id=trace_id)
                    counts["rounds"] += 1
        if kind in ("knowledge_query", "entity_search"):
            for e in reply.get("entities") or []:
                if isinstance(e, dict) and e.get("id"):
                    self.upsert_entity(e, provider, trace_id=trace_id)
                    counts["entities"] += 1
        if kind == "entity_get" and reply.get("id"):
            self.upsert_entity(reply, provider, trace_id=trace_id)
            counts["entities"] += 1
        if kind == "knowledge_search":
            counts["sources"] = self._record_search(request, reply, provider, trace_id)
        return counts

    def _record_search(self, request, reply, provider, trace_id) -> int:
        added = 0
        with self._connect() as db:
            companies = [(r["id"], r["company"]) for r in db.execute("SELECT id, company FROM funding_rounds")]
            claims = {c.get("id"): str(c.get("content") or "") for c in reply.get("context") or []
                      if isinstance(c, dict)}
            for c in reply.get("context") or []:
                if not isinstance(c, dict):
                    continue
                sources = [s for s in (_origin_source(o) for o in c.get("origins") or []) if s]
                text = claims.get(c.get("id"), "").casefold()
                owners = [rid for rid, name in companies
                          if len(name) >= 3 and re.search(r"(?<!\w)" + re.escape(name.casefold()) + r"(?!\w)", text)]
                if not owners:  # keep it under the question, so the source is not lost
                    q = (request or {}).get("input") if isinstance(request, dict) else None
                    owners = ["q:" + hashlib.sha1(str(q).encode()).hexdigest()[:16]]
                    table = "knowledge_search"
                else:
                    table = "funding_rounds"
                for owner in owners:
                    added += self._add_sources(db, table, owner, sources, provider, trace_id)
        return added

    def cala_hook(self, trace_id=None):
        """For `venus.cala.Cala(on_result=db.cala_hook(trace_id))`."""
        return lambda kind, request, reply: self.record_cala(kind, request, reply, trace_id=trace_id)

    # -- snapshots -----------------------------------------------------------------------------------------------

    def put_snapshot(self, kind: str, key: str, payload, mode: str = "live", trace_id=None) -> str:
        table = SNAPSHOT_TABLES.get(kind)
        if table is None:
            raise DbError(f"unknown snapshot kind {kind!r}; known: {sorted(SNAPSHOT_TABLES)}")
        if mode not in MODES:
            raise DbError(f"mode must be one of {MODES}, got {mode!r}")
        synthetic = ["*"] if mode == "simulated" else SYNTHETIC_FIELDS[kind]
        sid = uuid.uuid4().hex
        with self._connect() as db:
            db.execute(f"INSERT INTO {table} VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (sid, key, mode, json.dumps(payload), json.dumps(synthetic), trace_id, _now()))
        return sid

    def latest_snapshot(self, kind: str, key: str) -> dict | None:
        table = SNAPSHOT_TABLES.get(kind)
        if table is None:
            raise DbError(f"unknown snapshot kind {kind!r}")
        with self._connect(write=False) as db:
            r = db.execute(f"SELECT * FROM {table} WHERE key = ? ORDER BY created_at DESC, rowid DESC LIMIT 1",
                           (key,)).fetchone()
        if r is None:
            return None
        return {"id": r["id"], "kind": kind, "key": r["key"], "mode": r["mode"], "payload": json.loads(r["payload"]),
                "syntheticFields": json.loads(r["synthetic_fields"]), "synthetic": r["mode"] == "simulated",
                "traceId": r["trace_id"], "createdAt": r["created_at"]}

    # -- app data (frontend lib/server/db.ts) ---------------------------------------------------------------------

    @staticmethod
    def _user(r) -> dict:
        return {"id": r["id"], "role": r["role"], "name": r["name"], "email": r["email"],
                "passwordHash": r["password_hash"], "founderId": r["founder_id"], "investorName": r["investor_name"],
                "createdAt": r["created_at"], "isDemo": bool(r["is_demo"])}

    def create_user(self, role, name, email, password_hash="", founder_id=None, investor_name=None,
                    is_demo=False) -> dict:
        uid = str(uuid.uuid4())
        try:
            with self._connect() as db:
                db.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                           (uid, role, name, email.strip().lower(), password_hash, founder_id, investor_name,
                            _now(), int(bool(is_demo))))
                return self._user(db.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone())
        except sqlite3.IntegrityError as e:
            raise DbError(f"user not created: {e}") from None

    def user_by_email(self, email: str) -> dict | None:
        with self._connect(write=False) as db:
            r = db.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()
        return self._user(r) if r else None

    def create_session(self, user_id: str, days: float = 30, token: str | None = None,
                       expires_at: str | None = None) -> str:
        """A session for `user_id`; `token`/`expires_at` come from the caller (the TS server sets the cookie), else a
        new random token valid for `days`."""
        token = token or secrets.token_hex(32)
        expires = _utc_iso(expires_at) if expires_at else (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
        try:
            with self._connect() as db:
                db.execute("INSERT INTO sessions VALUES (?, ?, ?)", (token, user_id, expires))
        except sqlite3.IntegrityError as e:
            raise DbError(f"session not created (the token already exists, or no such user): {e}") from None
        return token

    def delete_session(self, token: str) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM sessions WHERE token = ?", (token,))

    def user_by_id(self, user_id: str) -> dict | None:
        with self._connect(write=False) as db:
            r = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return self._user(r) if r else None

    def set_investor_name(self, user_id: str, name: str) -> None:
        """The fund an investor user represents (frontend setInvestorFund)."""
        with self._connect() as db:
            cur = db.execute("UPDATE users SET investor_name = ? WHERE id = ? AND role = 'investor'", (name, user_id))
            if cur.rowcount != 1:
                raise DbError(f"no investor user {user_id!r}")

    def link_founder(self, user_id: str, founder_id: str) -> None:
        """Point a founder user at their founder record (frontend upsertFounderForUser)."""
        with self._connect() as db:
            cur = db.execute("UPDATE users SET founder_id = ? WHERE id = ? AND role = 'founder'", (founder_id, user_id))
            if cur.rowcount != 1:
                raise DbError(f"no founder user {user_id!r}")

    def investor_names(self) -> list:
        """The funds investor users represent (distinct, sorted); a profile key investor:<slug> maps back to one."""
        with self._connect(write=False) as db:
            return [r[0] for r in db.execute("SELECT DISTINCT investor_name FROM users WHERE role = 'investor' "
                                             "AND investor_name IS NOT NULL AND investor_name != '' ORDER BY 1")]

    def founder(self, founder_id: str) -> dict | None:
        with self._connect(write=False) as db:
            r = db.execute("SELECT * FROM founders WHERE id = ?", (founder_id,)).fetchone()
        return self._founder(r) if r else None

    def session_user(self, token: str) -> dict | None:
        with self._connect(write=False) as db:
            r = db.execute("SELECT users.* FROM sessions JOIN users ON users.id = sessions.user_id "
                           "WHERE sessions.token = ? AND sessions.expires_at > ?", (token, _now())).fetchone()
        return self._user(r) if r else None

    @staticmethod
    def _founder(r) -> dict:
        return {"id": r["id"], "profile": json.loads(r["profile"]), "founderName": r["founder_name"],
                "email": r["email"], "discoverable": bool(r["discoverable"]), "updatedAt": r["updated_at"]}

    def upsert_founder(self, record: dict) -> dict:
        fid = record.get("id") or str(uuid.uuid4())
        with self._connect() as db:
            db.execute("""INSERT INTO founders VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (id) DO UPDATE SET
                profile = excluded.profile, founder_name = excluded.founder_name, email = excluded.email,
                discoverable = excluded.discoverable, updated_at = excluded.updated_at""",
                       (fid, json.dumps(record.get("profile") or {}), record.get("founderName"), record.get("email"),
                        int(bool(record.get("discoverable"))), _now()))
            return self._founder(db.execute("SELECT * FROM founders WHERE id = ?", (fid,)).fetchone())

    def discoverable_founders(self) -> list:
        with self._connect(write=False) as db:
            return [self._founder(r) for r in db.execute("SELECT * FROM founders WHERE discoverable = 1 "
                                                         "ORDER BY updated_at DESC").fetchall()]

    @staticmethod
    def _intro(r) -> dict:
        d = {"id": r["id"], "founderId": r["founder_id"], "investor": r["investor"], "direction": r["direction"],
             "note": r["note"] or "", "status": r["status"], "createdAt": r["created_at"]}
        if r["pass_reason"]:
            d["passReason"] = r["pass_reason"]
        if r["responded_at"]:
            d["respondedAt"] = r["responded_at"]
        return d

    def create_intro(self, founder_id: str, investor: str, direction: str, note: str = "") -> dict:
        """A new pending intro, or the pending one that already exists between this founder and investor."""
        try:
            with self._connect() as db:
                r = db.execute("SELECT * FROM intros WHERE founder_id = ? AND investor = ? COLLATE NOCASE "
                               "AND status = 'pending'", (founder_id, investor)).fetchone()
                if r:
                    return self._intro(r)
                iid = str(uuid.uuid4())
                db.execute("INSERT INTO intros VALUES (?, ?, ?, ?, ?, 'pending', NULL, ?, NULL)",
                           (iid, founder_id, investor, direction, note, _now()))
                return self._intro(db.execute("SELECT * FROM intros WHERE id = ?", (iid,)).fetchone())
        except sqlite3.IntegrityError as e:
            raise DbError(f"intro not created: {e}") from None

    def respond_intro(self, intro_id: str, user_id: str, status: str, pass_reason: str | None = None) -> dict:
        """Accept or pass. Only the recipient may answer: the fund for founder-to-investor, the founder otherwise."""
        if status not in ("accepted", "passed"):
            raise DbError("status must be accepted or passed")
        with self._connect() as db:
            intro = db.execute("SELECT * FROM intros WHERE id = ?", (intro_id,)).fetchone()
            user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if intro is None or user is None:
                raise DbError("no such intro or user")
            if intro["status"] != "pending":
                raise DbError(f"intro already {intro['status']}")
            if intro["direction"] == "founder-to-investor":
                ok = user["role"] == "investor" and (user["investor_name"] or "").casefold() == intro["investor"].casefold()
            else:
                ok = user["role"] == "founder" and user["founder_id"] == intro["founder_id"]
            if not ok:
                raise DbError("only the recipient can answer this intro")
            db.execute("UPDATE intros SET status = ?, pass_reason = ?, responded_at = ? WHERE id = ?",
                       (status, pass_reason if status == "passed" else None, _now(), intro_id))
            return self._intro(db.execute("SELECT * FROM intros WHERE id = ?", (intro_id,)).fetchone())

    def intros(self, founder_id=None, investor=None) -> list:
        sql, args = "SELECT * FROM intros WHERE 1 = 1", []
        if founder_id:
            sql += " AND founder_id = ?"
            args.append(founder_id)
        if investor:
            sql += " AND investor = ? COLLATE NOCASE"
            args.append(investor)
        with self._connect(write=False) as db:
            return [self._intro(r) for r in db.execute(sql + " ORDER BY created_at DESC", args).fetchall()]

    # -- lookups for the service ---------------------------------------------------------------------------------

    def search_entities(self, name: str, limit: int = 8) -> list:
        """Names containing `name` (ignoring case): Cala entities first, then companies and investors seen in rounds
        that no entity already names. -> [{id, name, entity_type}] (the frontend's CalaEntity)."""
        needle = (name or "").strip().casefold()
        if not needle:
            return []
        hits, seen = [], set()

        def add(eid, label, kind):
            if label and needle in label.casefold() and label.casefold() not in seen:
                seen.add(label.casefold())
                hits.append({"id": eid, "name": label, "entity_type": kind})

        with self._connect(write=False) as db:
            for r in db.execute("SELECT id, name, entity_type FROM entities ORDER BY name"):
                add(r["id"], r["name"], r["entity_type"] or "Entity")
            for r in db.execute("SELECT company, lead_investors, other_investors FROM funding_rounds ORDER BY company"):
                add(f"company:{_slug(r['company'])}", r["company"], "Company")
                for inv in json.loads(r["lead_investors"]) + json.loads(r["other_investors"]):
                    add(f"investor:{_slug(inv)}", inv, "Investor")
        return hits[:max(0, int(limit))]

    # -- background jobs -------------------------------------------------------------------------------------------

    @staticmethod
    def _job(r) -> dict:
        return {k: r[k] for k in ("id", "kind", "subject_key", "status", "attempts", "error", "trace_id",
                                  "created_at", "started_at", "finished_at")}

    def enqueue_job(self, kind: str, subject_key: str) -> dict:
        """Queue a job, or return the job of the same kind for the same subject that is already waiting. A running
        job does not count: it may be working from data older than this request, so one more run waits after it."""
        if kind not in JOB_KINDS:
            raise DbError(f"job kind must be one of {JOB_KINDS}, got {kind!r}")
        with self._connect() as db:
            r = db.execute("SELECT * FROM jobs WHERE kind = ? AND subject_key = ? AND status = 'queued' "
                           "ORDER BY created_at, rowid LIMIT 1", (kind, subject_key)).fetchone()
            if r:
                return self._job(r)
            jid = uuid.uuid4().hex
            db.execute("INSERT INTO jobs (id, kind, subject_key, status, attempts, created_at) "
                       "VALUES (?, ?, ?, 'queued', 0, ?)", (jid, kind, subject_key, _now()))
            return self._job(db.execute("SELECT * FROM jobs WHERE id = ?", (jid,)).fetchone())

    def claim_job(self) -> dict | None:
        """Take the oldest queued job and mark it running, in one write transaction (no two workers get it)."""
        with self._connect() as db:
            r = db.execute("SELECT id FROM jobs WHERE status = 'queued' ORDER BY created_at, rowid LIMIT 1").fetchone()
            if r is None:
                return None
            db.execute("UPDATE jobs SET status = 'running', attempts = attempts + 1, started_at = ?, error = NULL "
                       "WHERE id = ?", (_now(), r["id"]))
            return self._job(db.execute("SELECT * FROM jobs WHERE id = ?", (r["id"],)).fetchone())

    def finish_job(self, job_id: str, error: str | None = None, trace_id: str | None = None,
                   attempt: int | None = None) -> bool:
        """Mark a running job done (or failed with `error`). With `attempt` (the claimed job's `attempts`), only that
        attempt may finish it: a run requeue_stale gave up on can't overwrite the retry. True when the row changed."""
        with self._connect() as db:
            cur = db.execute("UPDATE jobs SET status = ?, error = ?, trace_id = COALESCE(?, trace_id), finished_at = ? "
                             "WHERE id = ? AND status = 'running' AND (? IS NULL OR attempts = ?)",
                             ("failed" if error else "done", error, trace_id, _now(), job_id, attempt, attempt))
            return cur.rowcount == 1

    def requeue_stale(self, older_than_s: float, max_attempts: int = 2) -> int:
        """Jobs left `running` longer than `older_than_s` (the worker stopped mid-job): queue them again, or mark them
        failed once they used `max_attempts`. Returns how many were queued again."""
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=older_than_s)).isoformat()
        with self._connect() as db:
            stale = db.execute("SELECT id, attempts FROM jobs WHERE status = 'running' AND started_at < ?",
                               (cutoff,)).fetchall()
            again = 0
            for r in stale:
                if r["attempts"] < max_attempts:
                    db.execute("UPDATE jobs SET status = 'queued' WHERE id = ?", (r["id"],))
                    again += 1
                else:
                    db.execute("UPDATE jobs SET status = 'failed', finished_at = ?, error = ? WHERE id = ?",
                               (_now(), f"abandoned after {r['attempts']} attempts (the worker stopped mid-job)",
                                r["id"]))
        return again

    def job_state(self, kind: str, subject_key: str) -> dict | None:
        """The newest job of this kind for this subject, or None."""
        with self._connect(write=False) as db:
            r = db.execute("SELECT * FROM jobs WHERE kind = ? AND subject_key = ? ORDER BY created_at DESC, rowid DESC "
                           "LIMIT 1", (kind, subject_key)).fetchone()
        return self._job(r) if r else None

    def job(self, job_id: str) -> dict | None:
        with self._connect(write=False) as db:
            r = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return self._job(r) if r else None

    def jobs_summary(self) -> dict:
        with self._connect(write=False) as db:
            counts = dict(db.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status").fetchall())
        return {s: counts.get(s, 0) for s in ("queued", "running", "done", "failed")}

    def data_providers(self) -> set:
        """The providers market data came from ("cala", "simulator", ...): the service's live/simulated mode."""
        with self._connect(write=False) as db:
            return {r[0] for r in db.execute("SELECT provider FROM funding_rounds UNION SELECT provider FROM "
                                             "fund_closes UNION SELECT provider FROM entities")}

    # -- profiles of users and their rankings ----------------------------------------------------------------------

    def profile_status(self, key: str) -> str:
        """"ready" (a profile is stored), else "building" (a profile job is queued or running), "failed" (the last
        profile job failed) or "none"."""
        with self._connect(write=False) as db:  # one snapshot: a profile stored mid-check can't be missed
            if db.execute("SELECT 1 FROM profiles WHERE key = ? LIMIT 1", (key,)).fetchone():
                return "ready"
            job = db.execute("SELECT status FROM jobs WHERE kind = 'profile' AND subject_key = ? "
                             "ORDER BY created_at DESC, rowid DESC LIMIT 1", (key,)).fetchone()
        if job is None:
            return "none"
        return {"queued": "building", "running": "building", "failed": "failed"}.get(job["status"], "none")

    def latest_profiles(self, kind: str) -> list:
        """The newest version of every user profile of one kind ("startup": founder:*, "investor": investor:*);
        training profiles (other keys) are left out."""
        prefix = PROFILE_PREFIX.get(kind)
        if prefix is None:
            raise DbError(f"kind must be one of {sorted(PROFILE_PREFIX)}, got {kind!r}")
        with self._connect(write=False) as db:
            rows = db.execute("SELECT p.key, p.version, p.created_at, p.profile, p.rating, p.changes FROM profiles p "
                              "WHERE substr(p.key, 1, ?) = ? AND p.version = "
                              "(SELECT MAX(version) FROM profiles q WHERE q.key = p.key) ORDER BY p.key",
                              (len(prefix), prefix)).fetchall()
        return [_record(tuple(r)) for r in rows]

    def put_ranking(self, subject_key: str, subject_version, candidates: list, payload: dict,
                    trace_id: str | None = None) -> str:
        rid = uuid.uuid4().hex
        with self._connect() as db:
            db.execute("INSERT INTO rankings VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (rid, subject_key, subject_version, json.dumps(candidates), json.dumps(payload), trace_id,
                        _now()))
        return rid

    def latest_ranking(self, subject_key: str) -> dict | None:
        with self._connect(write=False) as db:
            r = db.execute("SELECT * FROM rankings WHERE subject_key = ? ORDER BY created_at DESC, rowid DESC LIMIT 1",
                           (subject_key,)).fetchone()
        if r is None:
            return None
        return {"id": r["id"], "subject_key": r["subject_key"], "subject_version": r["subject_version"],
                "candidates": json.loads(r["candidates"]), "payload": json.loads(r["payload"]),
                "trace_id": r["trace_id"], "created_at": r["created_at"]}
