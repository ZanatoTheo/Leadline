"""Seed the Leadline database from the cached Cala pull: market data, demo accounts, and their profile jobs.

    venus/.venv/bin/python scripts/seed_db.py --db leadline/data/leadline.db [--max-founders 10] [--max-investors 10]
                                              [--dry-run] [--build]

Cala is read from the disk cache only (app/data/cache): every query must be cached, and no request is ever sent (an
uncached query stops the seed before any request). It then:
- stores every round and entity of the pull (provider "cala");
- makes one demo founder per company whose sector and country map to the frontend's enums (types.ts Sector, Region),
  with a FounderProfile filled from the row; others are skipped and listed;
- makes one demo investor per investor named in the pull: leads first, then by the number of rounds they are in;
- adds the frontend's two demo logins (demo-founder@ / demo-investor@leadline.local);
- queues one profile job per account that has no profile yet. A rerun adds nothing.

The report (JSON on stdout) gives the counts and the cost of building the queued jobs. `--build` runs them now with the
worker, with Cala off (LEADLINE_LIVE_CALA is dropped): each profile job then queues its rank job, which also runs.
A live --build spends base-model and Context.dev calls: check the --dry-run estimate first.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT / "leadline", ROOT / "app"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import shapes  # noqa: E402
from build_cases import NOT_DISCLOSED, _cala_client, _NoNetwork  # noqa: E402
from db import LeadlineDb, _slug, deal_from_row  # noqa: E402
from ingest.build_dataset import QUERIES as _QUERIES  # noqa: E402
from service import SECTOR_WORDS, in_region, in_sector  # noqa: E402

QUERIES = list(_QUERIES)
CACHE_DIR = ROOT / "app" / "data" / "cache"
SECTORS = tuple(SECTOR_WORDS)  # types.ts order: climate, fintech, ai, health, saas
REGIONS = ("uk", "dach", "nordics", "europe")  # most specific first; types.ts lists europe, nordics, uk, dach
REGION_ORDER = ("europe", "nordics", "uk", "dach")
STAGES = ("pre-seed", "seed", "series-a", "series-b")
LATE_STAGES = {"series-c", "series-d", "series-e", "growth", "late"}  # beyond the frontend's last stage
DEMO_PERSONA = {"startupName": "Carbonlens", "oneLiner": "Measures and cuts Scope 3 emissions for mid-size manufacturers",
                "sector": "climate", "stage": "seed", "location": "Berlin, Germany", "region": "europe",
                "raiseEurM": 1.5, "competitors": ["Tracely"], "customers": "mid-size manufacturers"}  # demo.ts
DEMO_FOUNDER = {"email": "demo-founder@leadline.local", "name": "Alex"}  # auth.ts DEMO
DEMO_INVESTOR = {"email": "demo-investor@leadline.local", "name": "Sam", "investorName": "Fjord Ventures"}
PER_RUN_MODEL_CALLS, PER_RUN_WEB_CALLS = 7, 6  # used when the strategy notes don't say


def cala_client(cache_dir, http):
    return _cala_client(cache_dir, http, None)


def load_replies(cache_dir, http) -> list:
    """[(query, reply)] from the cache. Raises LookupError, before any request, when a query is not cached."""
    client = cala_client(cache_dir, http)
    url = f"{client.base_url}/v1/knowledge/query"
    missing = [q for q in QUERIES
               if not client._cache_path("POST", url, None, {"input": q, "return_entities": True}).exists()]
    if missing:
        raise LookupError(f"{len(missing)} of {len(QUERIES)} Cala queries are not cached in {cache_dir}: {missing}")
    return [(q, client.knowledge_query(q)) for q in QUERIES]


def _real(name) -> bool:
    return bool(name) and name.strip().casefold() not in NOT_DISCLOSED


def sector_of(industry):
    return next((s for s in SECTORS if in_sector(industry, s)), None)


def region_of(country):
    return next((r for r in REGIONS if in_region(country, r)), None)


def founder_profile(deal: dict) -> tuple:
    """(FounderProfile, assumed): what the row doesn't say is filled in, and each guess is listed in `assumed`
    ({company, field, value}) so the report shows it."""
    stage = _slug(deal.get("round") or "")
    country = deal.get("country") or ""
    assumed = []
    if stage not in STAGES:
        assumed.append({"company": deal["company"], "field": "stage", "value": deal.get("round")})
        stage = "series-b" if stage in LATE_STAGES else "seed"
    raise_eur_m = deal.get("amountEurM")
    if not raise_eur_m:
        assumed.append({"company": deal["company"], "field": "raiseEurM", "value": raise_eur_m})
    one_liner = (deal.get("companyDescription") or "").strip() or \
        f"{deal.get('industry') or 'Startup'} company in {country}"
    return ({"startupName": deal["company"], "oneLiner": one_liner, "sector": sector_of(deal.get("industry")),
             "stage": stage, "location": country, "region": region_of(country),
             "raiseEurM": float(raise_eur_m or 1.0), "competitors": [], "customers": ""}, assumed)


def plan(deals: list, max_founders: int, max_investors: int) -> dict:
    """Which companies become founders (and which are skipped, why) and which investors become accounts."""
    newest = {}  # one founder per company slug (its emails and keys come from the slug): the newest round wins
    for d in sorted(deals, key=lambda d: d["announced"], reverse=True):
        newest.setdefault(shapes.slugify(d["company"]), d)
    founders, skipped = [], []
    for d in newest.values():
        company = d["company"]
        if sector_of(d.get("industry")) is None:
            skipped.append({"company": company, "reason": f"sector {d.get('industry')!r} is none of "
                                                          f"{', '.join(SECTORS)}"})
        elif region_of(d.get("country")) is None:
            skipped.append({"company": company, "reason": f"country {d.get('country')!r} is in none of "
                                                          f"{', '.join(REGION_ORDER)}"})
        else:
            founders.append(d)
    rounds, leads = {}, set()
    for d in deals:
        for name in d.get("leadInvestors") or []:
            if _real(name):
                leads.add(name)
                rounds[name] = rounds.get(name, 0) + 1
        for name in d.get("otherInvestors") or []:
            if _real(name):
                rounds[name] = rounds.get(name, 0) + 1
    investors, slugs = [], set()  # one account per fund slug ("Seedcamp" == "SeedCamp"): the first in order wins
    for name in sorted(rounds, key=lambda n: (n not in leads, -rounds[n], n.casefold())):
        if shapes.slugify(name) and shapes.slugify(name) not in slugs:
            slugs.add(shapes.slugify(name))
            investors.append(name)
    keep_f, keep_i = max(0, max_founders), max(0, max_investors)
    return {"founders": founders[:keep_f], "skipped": skipped, "investors": investors[:keep_i],
            "left_out": {"founders": max(0, len(founders) - keep_f), "investors": max(0, len(investors) - keep_i)}}


def _limits() -> tuple:
    """Per-run model / web call maxima seen when the profile strategy was validated (its notes)."""
    try:
        data = json.loads((ROOT / "leadline" / "strategies" / "leadline-profile-default.json").read_text())
        metrics = json.loads(data["notes"])["gate"]["metrics"]
        return int(metrics["model_calls_per_case_max"]), int(metrics["web_calls_per_case_max"])
    except (OSError, KeyError, ValueError, TypeError):
        return PER_RUN_MODEL_CALLS, PER_RUN_WEB_CALLS


class Seeder:
    def __init__(self, db: LeadlineDb, dry_run: bool):
        self.db, self.dry_run = db, dry_run
        self.created, self.queued, self.pending = 0, 0, 0
        self._seen_emails = set()

    def _account(self, email: str):
        """The existing user, or None when it will be made (counted once per email)."""
        user = self.db.user_by_email(email)
        if user is None and email not in self._seen_emails:
            self._seen_emails.add(email)
            self.created += 1
        return user

    def _queue(self, key: str | None) -> None:
        status = self.db.profile_status(key) if key else "none"
        if status != "ready":
            self.pending += 1  # a profile --build would run (now or already queued)
        if status in ("none", "failed"):  # a failed first build is tried again
            self.queued += 1
            if not self.dry_run:
                self.db.enqueue_job("profile", key)

    def founder(self, email: str, name: str, profile: dict) -> None:
        user = self._account(email)
        if self.dry_run:
            self._queue(shapes.profile_key_founder(user["founderId"]) if user and user.get("founderId") else None)
            return
        if user is None:
            user = self.db.create_user("founder", name, email, "", is_demo=True)
        if not user.get("founderId"):
            record = self.db.upsert_founder({"profile": profile, "founderName": name, "email": email,
                                             "discoverable": True})
            self.db.link_founder(user["id"], record["id"])
            user = self.db.user_by_id(user["id"])
        self._queue(shapes.profile_key_founder(user["founderId"]))

    def investor(self, email: str, name: str, investor_name: str) -> None:
        user = self._account(email)
        key = shapes.profile_key_investor(investor_name)
        if not self.dry_run:
            if user is None:
                user = self.db.create_user("investor", name, email, "", is_demo=True)
            if not user.get("investorName"):
                self.db.set_investor_name(user["id"], investor_name)
        self._queue(key)


def seed(db: LeadlineDb, replies: list, max_founders: int, max_investors: int, dry_run: bool) -> dict:
    deals_by_id, entity_ids, rows = {}, set(), 0
    for _, reply in replies:
        for row in reply.get("results") or []:
            rows += 1
            deal = deal_from_row(row)
            if deal:
                deals_by_id[deal["id"]] = deal
        entity_ids |= {e["id"] for e in reply.get("entities") or [] if isinstance(e, dict) and e.get("id")}
    if not dry_run:
        for query, reply in replies:
            db.record_cala("knowledge_query", {"input": query}, reply, trace_id="seed")
    chosen = plan(list(deals_by_id.values()), max_founders, max_investors)

    s, assumed = Seeder(db, dry_run), []
    for d in chosen["founders"]:
        profile, guesses = founder_profile(d)
        assumed += guesses
        s.founder(f"seed-{shapes.slugify(d['company'])}@leadline.local", d["company"], profile)
    for name in chosen["investors"]:
        s.investor(f"seed-investor-{shapes.slugify(name)}@leadline.local", name, name)
    s.founder(DEMO_FOUNDER["email"], DEMO_FOUNDER["name"], DEMO_PERSONA)
    s.investor(DEMO_INVESTOR["email"], DEMO_INVESTOR["name"], DEMO_INVESTOR["investorName"])

    model_max, web_max = _limits()
    # rows: as Cala sent them; rounds: those with a company and a single date (a "2025–2026" range is no round)
    return {"dry_run": dry_run, "cala_calls": 0, "rows": rows, "rounds": len(deals_by_id), "entities": len(entity_ids),
            "founders": [d["company"] for d in chosen["founders"]], "investors": chosen["investors"],
            "skipped": chosen["skipped"], "left_out": chosen["left_out"], "assumed": assumed,
            "accounts_created": s.created, "jobs_queued": s.queued,
            "estimate": {"profile_jobs": s.pending, "rank_jobs": s.pending, "cala_calls": 0,
                         "model_calls_max": 2 * s.pending * model_max, "context_dev_calls_max": s.pending * web_max,
                         "note": "upper bounds from the validated strategy's per-run maxima; rank jobs use no web"}}


def build(db: LeadlineDb, environ: dict, model=None) -> dict:
    """Run every queued job (profile jobs queue their rank jobs) with Cala off."""
    from jobs import Worker, handlers, make_agents
    env = {k: v for k, v in environ.items() if k != "LEADLINE_LIVE_CALA"}
    profile_agent, match_agent = make_agents(env, model=model)
    worker = Worker(db, handlers(profile_agent, match_agent))
    worker.recover()
    counts = {"done": 0, "failed": 0}
    while (job := worker.run_once()) is not None:
        counts[job["status"]] = counts.get(job["status"], 0) + 1
    return counts


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--db", default=str(ROOT / "leadline" / "data" / "leadline.db"))
    p.add_argument("--cache-dir", default=str(CACHE_DIR))
    p.add_argument("--max-founders", type=int, default=10)
    p.add_argument("--max-investors", type=int, default=10)
    p.add_argument("--dry-run", action="store_true", help="report what would be written; write nothing")
    p.add_argument("--build", action="store_true", help="run the queued jobs now (spends model/Context.dev calls)")
    return p.parse_args(argv)


def main(argv=None, *, cala_http=None, model=None, environ=None) -> int:
    args = parse_args(argv)
    try:
        replies = load_replies(args.cache_dir, cala_http or _NoNetwork())
    except LookupError as e:
        print(f"seed_db: {e}", file=sys.stderr)
        return 2
    if args.dry_run:  # opening a LeadlineDb migrates it and turns on WAL: a dry run reads a temporary copy
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "dry-run.db"
            if Path(args.db).exists():
                with sqlite3.connect(f"file:{Path(args.db).resolve()}?mode=ro", uri=True) as src, \
                        sqlite3.connect(copy) as dst:
                    src.backup(dst)
            report = seed(LeadlineDb(copy), replies, args.max_founders, args.max_investors, True)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0
    db = LeadlineDb(args.db)
    report = seed(db, replies, args.max_founders, args.max_investors, False)
    if args.build and not args.dry_run:
        report["build"] = build(db, dict(os.environ if environ is None else environ), model=model)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
