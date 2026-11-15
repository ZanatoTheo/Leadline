"""The local HTTP service the frontend's server code calls (frontend/src/lib/server/leadline-service.ts).

    app = create_app(LeadlineDb("leadline/data/leadline.db"), worker)   # served by serve.py on 127.0.0.1 only

Page loads only read the database here: no endpoint calls Cala, the web or a model. Writes that need the agent
(a new user's profile, a ranking that is out of date) queue a job for the worker instead. Every body is in the
frontend's own types (built by shapes.*_out, checked against contracts/schemas/ in tests); errors are
{"error": "..."} with 400/401/403/404/409/503.

The service trusts its caller (the TS server has already checked the session cookie). Locally it binds 127.0.0.1
only; when it is exposed (serve.py --host 0.0.0.0), set LEADLINE_SERVICE_TOKEN so every route but /healthz needs
`authorization: Bearer <token>`.
"""
from __future__ import annotations

import hmac
import json
import os
import re
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path

import jsonschema
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

import ranking
import shapes
from db import DbError

SCHEMAS = Path(__file__).resolve().parents[1] / "contracts" / "schemas"
ROLES = ("founder", "investor")
DIRECTIONS = ("founder-to-investor", "investor-to-founder")
ANSWERS = ("accepted", "passed")
STAGES = ("pre-seed", "seed", "series-a", "series-b")  # types.ts Stage

# types.ts Sector -> words that mark an industry as that sector (whole words, so "ai" never matches "retail").
SECTOR_WORDS = {
    "climate": {"climate", "climatetech", "cleantech", "clean", "energy", "renewable", "renewables", "sustainability",
                "greentech", "fusion", "carbon", "ocean", "circular", "battery", "batteries", "solar", "wind",
                "hydrogen"},
    "fintech": {"fintech", "finance", "financial", "banking", "payments", "payment", "insurtech", "insurance",
                "lending", "wealthtech", "crypto", "blockchain", "remittances", "regtech"},
    "ai": {"ai", "artificial", "ml", "llm", "llms", "genai", "deeptech", "chips", "semiconductors", "machine"},
    "health": {"health", "healthtech", "healthcare", "medtech", "medical", "biotech", "pharma", "therapeutics",
               "diagnostics"},
    "saas": {"saas", "software", "enterprise", "b2b", "devtools", "commerce", "ecommerce"},
}
STOP_WORDS = {"with", "that", "from", "this", "their", "they", "about", "into", "based", "using", "startup",
              "startups", "company", "companies", "platform", "solution", "solutions", "which", "where", "your"}


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def _words(text) -> list:
    return re.findall(r"[a-z0-9]+", str(text or "").casefold())


def _content_words(text) -> set:
    return {w for w in _words(text) if len(w) >= 4 and w not in STOP_WORDS}


def in_sector(industry, sector: str) -> bool:
    return bool(SECTOR_WORDS[sector] & set(_words(industry)))


def _region_places() -> dict:
    pf = ranking._prefilter()
    return {"europe": pf.EUROPE | {"europe", "eu"}, "nordics": pf.NORDICS | {"nordics", "nordic", "scandinavia"},
            "uk": {"united kingdom", "ireland", "uk & ireland"}, "dach": {"germany", "austria", "switzerland", "dach"}}


def in_region(country, region: str) -> bool:
    """types.ts Region -> the countries it covers (the prefilter's groups). A round with no country never matches."""
    return bool(country) and ranking._prefilter()._place(country) in _region_places()[region]


# --- request parsing ----------------------------------------------------------------------------------------------

async def _body(request: Request) -> dict:
    try:
        body = await request.json()
    except Exception:
        raise ApiError(400, "the body must be JSON") from None
    if not isinstance(body, dict):
        raise ApiError(400, "the body must be a JSON object")
    return body


def _text(body: dict, name: str, required: bool = True) -> str | None:
    value = body.get(name)
    if value is None and not required:
        return None
    if not isinstance(value, str) or (required and not value.strip()):
        raise ApiError(400, f"{name} must be a non-empty string")
    return value


def _choice(value, name: str, options) -> str:
    if value not in options:
        raise ApiError(400, f"{name} must be one of {list(options)}, got {value!r}")
    return value


def _since(params) -> str | None:
    raw = params.get("sinceDays")
    if raw in (None, ""):
        return None
    try:
        days = int(raw)
    except ValueError:
        raise ApiError(400, "sinceDays must be a whole number") from None
    if not 0 <= days <= 36_500:
        raise ApiError(400, "sinceDays must be between 0 and 36500")
    return (date.today() - timedelta(days=days)).isoformat()


def _schema(name: str):
    return jsonschema.Draft7Validator(json.loads((SCHEMAS / f"{name}.json").read_text()))


def create_app(db, worker=None, *, token=None) -> FastAPI:
    """token: the bearer token every route but /healthz needs (default: LEADLINE_SERVICE_TOKEN; "" forces auth off)."""
    founder_profile = _schema("FounderProfile")

    @asynccontextmanager
    async def lifespan(app):
        if worker is not None:
            worker.start()
        try:
            yield
        finally:
            if worker is not None:
                worker.stop()

    app = FastAPI(title="Leadline service", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.db, app.state.worker = db, worker

    service_token = os.environ.get("LEADLINE_SERVICE_TOKEN") if token is None else token
    if service_token:

        @app.middleware("http")
        async def _auth(request, call_next):
            expected = f"Bearer {service_token}"
            got = request.headers.get("authorization", "")
            if request.url.path != "/healthz" and not hmac.compare_digest(got.encode(), expected.encode()):
                return JSONResponse({"error": "missing or wrong service token"}, status_code=401)
            return await call_next(request)

    @app.get("/healthz")
    def healthz():
        """Deploy health check; always open, touches nothing."""
        return {"ok": True}

    @app.exception_handler(ApiError)
    async def _api_error(request, exc: ApiError):
        return JSONResponse({"error": exc.message}, status_code=exc.status)

    @app.exception_handler(DbError)
    async def _db_error(request, exc: DbError):
        return JSONResponse({"error": str(exc)}, status_code=400)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request, exc: StarletteHTTPException):
        return JSONResponse({"error": str(exc.detail)}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request, exc: RequestValidationError):
        return JSONResponse({"error": str(exc.errors()[:1])}, status_code=400)

    # -- helpers that need the db --------------------------------------------------------------------------------

    def user_or_404(user_id: str) -> dict:
        user = db.user_by_id(user_id)
        if user is None:
            raise ApiError(404, f"no user {user_id!r}")
        return user

    def check_profile(profile) -> dict:
        errors = sorted(founder_profile.iter_errors(profile), key=lambda e: list(e.path))
        if errors:
            where = "/".join(str(p) for p in errors[0].path) or "profile"
            raise ApiError(400, f"profile is not a FounderProfile: {where}: {errors[0].message}")
        return profile

    def queue_profile(key: str) -> None:
        """A first profile build only (editing is out of scope, so a stored profile is left as is). A failed first
        build is queued again here, on the user's next save; page loads never retry it. The same holds for a failed
        ranking of a stored profile: the next save queues one rank job (a queued one is reused, never doubled)."""
        status = db.profile_status(key)
        if status in ("none", "failed"):
            db.enqueue_job("profile", key)
        elif status == "ready":
            rank = db.job_state("rank", key)
            if rank is not None and rank["status"] == "failed":
                db.enqueue_job("rank", key)

    def user_key(key: str) -> str:
        try:
            ranking.subject_kind(key)
        except ValueError:
            raise ApiError(400, f"not a user profile key: {key!r} (founder:<id> or investor:<slug>)") from None
        return key

    # -- accounts ------------------------------------------------------------------------------------------------

    @app.post("/users")
    async def create_user(request: Request):
        body = await _body(request)
        role = _choice(body.get("role"), "role", ROLES)
        name, email = _text(body, "name").strip(), _text(body, "email").strip().lower()
        password_hash = body.get("passwordHash") or ""
        if not isinstance(password_hash, str):
            raise ApiError(400, "passwordHash must be a string")
        if db.user_by_email(email) is not None:
            raise ApiError(409, "An account with this email already exists.")
        return shapes.user_out(db.create_user(role, name, email, password_hash))

    @app.get("/users/by-email")
    def user_by_email(email: str = ""):
        user = db.user_by_email(email) if email.strip() else None
        if user is None:
            raise ApiError(404, "no user with this email")
        return shapes.user_out(user)

    @app.get("/users/{user_id}")
    def get_user(user_id: str):
        return shapes.user_out(user_or_404(user_id))

    @app.post("/sessions", status_code=204)
    async def create_session(request: Request):
        body = await _body(request)
        user_or_404(_text(body, "userId"))
        try:
            db.create_session(body["userId"], token=_text(body, "token"), expires_at=_text(body, "expiresAt"))
        except DbError as e:
            raise ApiError(409 if "already exists" in str(e) else 400, str(e)) from None
        return Response(status_code=204)

    @app.get("/sessions/{token}")
    def get_session(token: str):
        user = db.session_user(token)
        if user is None:
            raise ApiError(404, "no such session, or it expired")
        founder = db.founder(user["founderId"]) if user.get("founderId") else None
        return {"user": shapes.user_out(user), "profile": founder["profile"] if founder else None,
                "discoverable": founder["discoverable"] if founder else True}

    @app.delete("/sessions/{token}", status_code=204)
    def delete_session(token: str):
        db.delete_session(token)
        return Response(status_code=204)

    @app.post("/demo-users")
    async def demo_user(request: Request):
        """The frontend's one-click demo accounts: made once, the founder with its persona record."""
        body = await _body(request)
        role = _choice(body.get("role"), "role", ROLES)
        email, name = _text(body, "email").strip().lower(), _text(body, "name").strip()
        persona = body.get("persona")
        if role == "founder":
            if persona is None:
                raise ApiError(400, "a demo founder needs a persona (FounderProfile)")
            check_profile(persona)
        investor_name = _text(body, "investorName", required=False)
        user = db.user_by_email(email)
        if user is None:
            user = db.create_user(role, name, email, "", is_demo=True)
        elif user["role"] != role:
            raise ApiError(409, f"{email} is already a {user['role']}")
        if role == "founder":
            if not user.get("founderId"):
                record = db.upsert_founder({"profile": persona, "founderName": name, "email": email,
                                            "discoverable": True})
                db.link_founder(user["id"], record["id"])
                user = db.user_by_id(user["id"])
            queue_profile(shapes.profile_key_founder(user["founderId"]))
        elif investor_name or user.get("investorName"):
            if not user.get("investorName"):
                db.set_investor_name(user["id"], investor_name.strip())
                user = db.user_by_id(user["id"])
            queue_profile(shapes.profile_key_investor(user["investorName"]))
        return shapes.user_out(user)

    # -- founders and funds --------------------------------------------------------------------------------------

    @app.put("/users/{user_id}/founder")
    async def put_founder(user_id: str, request: Request):
        user = user_or_404(user_id)
        if user["role"] != "founder":
            raise ApiError(403, "This is only for founders.")
        body = await _body(request)
        profile = check_profile(body.get("profile"))
        discoverable = body.get("discoverable")
        if not isinstance(discoverable, bool):
            raise ApiError(400, "discoverable must be true or false")
        record = db.upsert_founder({"id": user.get("founderId"), "profile": profile,
                                    "founderName": _text(body, "founderName", required=False) or "",
                                    "email": _text(body, "email", required=False) or "", "discoverable": discoverable})
        if not user.get("founderId"):
            db.link_founder(user_id, record["id"])
        queue_profile(shapes.profile_key_founder(record["id"]))
        return shapes.founder_record_out(record)

    @app.put("/users/{user_id}/investor-fund", status_code=204)
    async def put_investor_fund(user_id: str, request: Request):
        user = user_or_404(user_id)
        if user["role"] != "investor":
            raise ApiError(403, "This is only for investors.")
        name = _text(await _body(request), "investorName").strip()
        db.set_investor_name(user_id, name)
        queue_profile(shapes.profile_key_investor(name))
        return Response(status_code=204)

    @app.get("/founders")
    def founders(discoverable: str = ""):
        if discoverable != "1":
            raise ApiError(400, "only discoverable=1 is supported")
        return [shapes.founder_record_out(f) for f in db.discoverable_founders()]

    @app.get("/founders/{founder_id}")
    def founder(founder_id: str):
        record = db.founder(founder_id)
        if record is None:
            raise ApiError(404, f"no founder {founder_id!r}")
        return shapes.founder_record_out(record)

    # -- intros --------------------------------------------------------------------------------------------------

    @app.post("/intros")
    async def create_intro(request: Request):
        body = await _body(request)
        founder_id = _text(body, "founderId")
        if db.founder(founder_id) is None:
            raise ApiError(404, f"no founder {founder_id!r}")
        direction = _choice(body.get("direction"), "direction", DIRECTIONS)
        note = body.get("note") or ""
        if not isinstance(note, str):
            raise ApiError(400, "note must be a string")
        return shapes.intro_out(db.create_intro(founder_id, _text(body, "investor").strip(), direction, note))

    @app.get("/intros")
    def intros(founderId: str = "", investor: str = ""):  # noqa: N803 (the frontend's names)
        return [shapes.intro_out(i) for i in db.intros(founder_id=founderId or None, investor=investor or None)]

    @app.patch("/intros/{intro_id}")
    async def answer_intro(intro_id: str, request: Request):
        body = await _body(request)
        status = _choice(body.get("status"), "status", ANSWERS)
        pass_reason = _text(body, "passReason", required=False)
        try:
            return shapes.intro_out(db.respond_intro(intro_id, _text(body, "userId"), status, pass_reason))
        except DbError as e:
            text = str(e)
            code = 404 if text.startswith("no such") else 403 if "recipient" in text else \
                409 if text.startswith("intro already") else 400
            raise ApiError(code, text) from None

    # -- market data (DB only) -----------------------------------------------------------------------------------

    @app.get("/deals")
    def deals(request: Request):
        q = request.query_params
        sector = _choice(q["sector"], "sector", SECTOR_WORDS) if q.get("sector") else None
        region = _choice(q["region"], "region", _region_places()) if q.get("region") else None
        stage = _choice(q["stage"], "stage", STAGES) if q.get("stage") else None
        rows = db.rounds(since=_since(q), stages=[stage] if stage else None)
        return [shapes.deal_out(r) for r in rows
                if (not sector or in_sector(r["industry"], sector)) and (not region or in_region(r["country"], region))]

    @app.get("/deals/investor")
    def deals_by_investor(request: Request):
        q = request.query_params
        name = _text(dict(q), "name")
        return [shapes.deal_out(r) for r in db.rounds(investor=name.strip(), since=_since(q))]

    @app.get("/deals/company")
    def deals_by_company(request: Request):
        name = _text(dict(request.query_params), "name")
        return [shapes.deal_out(r) for r in db.rounds(company=name.strip())]

    @app.get("/deals/similar")
    def similar(request: Request):
        """Every round of the companies whose description or industry shares 2+ content words with the query; same
        sector first, then more shared words, then the newest round."""
        q = request.query_params
        wanted = _content_words(_text(dict(q), "description"))
        sector = _choice(q["sector"], "sector", SECTOR_WORDS) if q.get("sector") else None
        by_company, score = {}, {}
        for r in db.rounds():
            by_company.setdefault(r["company"], []).append(r)
            shared = len(wanted & _content_words(f"{r['companyDescription'] or ''} {r['industry'] or ''}"))
            if shared >= 2:
                same = bool(sector) and in_sector(r["industry"], sector)
                score[r["company"]] = max(score.get(r["company"], (False, 0, "")), (same, shared, r["announced"]))
        order = sorted(score, key=lambda c: score[c], reverse=True)
        return [shapes.deal_out(r) for c in order for r in by_company[c]]

    def closes(investor=None, since=None, sector=None) -> list:
        out = []
        for row in db.fund_closes(investor=investor):
            close = shapes.fund_close_out(row)
            if close is None or (since and close["closed"] < since):
                continue
            if sector and not (in_sector(close["fundName"], sector) or
                               any(in_sector(d["industry"], sector) for d in db.rounds(investor=close["investor"]))):
                continue
            out.append(close)
        return out

    @app.get("/funds")
    def funds(investor: str = ""):
        return closes(investor=investor.strip() or None)

    @app.get("/fund-closes")
    def fund_closes(request: Request):
        """Recent fund closes; with a sector, those whose fund name names it or whose investor has rounds in it."""
        q = request.query_params
        sector = _choice(q["sector"], "sector", SECTOR_WORDS) if q.get("sector") else None
        return closes(since=_since(q), sector=sector)

    @app.get("/entities")
    def entities(name: str = "", limit: int = 8):
        return [shapes.entity_out(e) for e in db.search_entities(name, limit=max(1, min(limit, 50)))]

    @app.get("/status")
    def status():
        jobs = db.jobs_summary()
        return {"mode": "live" if "cala" in db.data_providers() else "simulated",
                "jobs": {k: jobs[k] for k in ("queued", "running", "failed")}}

    # -- agent results (stored; never computed here) -------------------------------------------------------------

    @app.get("/profiles/{key}")
    def profile(key: str):
        state = db.profile_status(user_key(key))
        out = {"status": state}
        if state == "ready":
            record = db.get(key)
            out.update(profile=record["profile"], rating=record["rating"], version=record["version"],
                       updatedAt=record["created_at"])
        elif state == "failed":
            out["error"] = (db.job_state("profile", key) or {}).get("error") or "the profile build failed"
        return out

    @app.get("/rankings/{key}")
    def rankings(key: str):
        """The stored ranking. When this user's best N changed, one rank job is queued (never more than one waits)
        and the old ranking is returned until the new one is stored."""
        subject = db.get(user_key(key))
        latest = db.latest_ranking(key)
        if subject is not None and ranking.needs_rerank(db, key):
            db.enqueue_job("rank", key)
        job = db.job_state("rank", key)
        if job is not None and job["status"] in ("queued", "running"):
            state = "building"
        elif latest is not None:
            state = "ready"
        elif job is not None and job["status"] == "failed":
            state = "failed"
        else:
            state = "building" if subject is None and db.profile_status(key) == "building" else "none"
        out = {"status": state, "ranking": None}
        if state == "failed":
            out["error"] = job["error"]
        if latest is not None:
            out["ranking"] = ranking_out(key, subject, latest)
        return out

    def ranking_out(key: str, subject, latest: dict) -> dict:
        payload = latest.get("payload") or {}
        selected, pool = ranking.current_top(db, key, subject, payload) if subject else ([], {})

        def about(candidate_key):
            record = pool.get(candidate_key) or db.get(candidate_key) or {}
            profile = record.get("profile") or {}
            return profile.get("name") or candidate_key, profile.get("kind")

        matches = []
        for m in payload.get("matches") or []:
            if m["candidate_id"] not in pool:  # gone since: a founder who stopped being discoverable, say
                continue
            name, kind = about(m["candidate_id"])
            matches.append({"key": m["candidate_id"], "name": name, "kind": kind, "score": m.get("score"),
                            "scoreParts": m.get("score_parts") or {}, "confidence": m.get("confidence"),
                            "reasons": m.get("reasons") or [], "rank": m.get("rank")})
        stored = {c["key"] for c in latest.get("candidates") or []}
        new = [{"key": k, "name": about(k)[0], "fit": fit} for k, fit in selected if k not in stored]
        return {"matches": matches, "newCandidates": new, "computedAt": latest["created_at"]}

    return app
