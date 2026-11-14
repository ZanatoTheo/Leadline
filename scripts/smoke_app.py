"""End-to-end smoke run of the built app against the real Leadline service, fully offline.

    venus/.venv/bin/python scripts/smoke_app.py [--only accounts|data|all] [--no-build] [--keep]

It makes a temp database, seeds it from the cached Cala replies (scripts/seed_db.py; no Cala call), starts `leadline/serve.py --fake-model` and `next start` on free 127.0.0.1 ports (neither
gets an API key), and drives the app through its /api routes the way the pages do, with a cookie jar per user. Every
body is checked against the frontend's types (contracts/schemas/). Guards loaded into Next and into every Python
process (seed, service) block and count any connection or DNS lookup that is not for 127.0.0.1, and the run fails
if there was one. The guards cover TCP connections and name lookups (getaddrinfo/gethostbyname, dns.lookup), not raw
UDP or other resolvers; nothing in the app uses those. `next build` (only when the sources changed) runs unguarded:
next/font/google in the fixed layout.tsx downloads its fonts at build time. Next telemetry is off for build and start.
It prints a route-by-route table and exits
1 on any failure.

Checks:
  accounts  signup, me, onboarding (founder profile), investor fund, intro both ways, answer, logout/login,
            duplicate signup, wrong password, demo logins
  data      a failed profile build gives a real error (not "being built" forever) until the profile is saved again;
            a new founder's shortlist is 202 (with the build step) while the agent builds it, then 200 with at most 10 ranked investors;
            as the demo founder: shortlist, investor brief, fit (agent score), twins, signals, funds, status;
            as the demo investor: discover, thesis, company and startup diligence
  (always)  with the service stopped, the routes answer JSON errors (503), not crashes
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
import uuid
from pathlib import Path

import httpx
import jsonschema

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
PYTHON = ROOT / "venus" / ".venv" / "bin" / "python"
SCHEMAS = ROOT / "contracts" / "schemas"
GUARD = ROOT / "scripts" / "smoke_guard.cjs"
PY_GUARD = ROOT / "scripts" / "smoke_pyguard"  # sitecustomize.py: the same guard for Python
SECRET_VARS = ("CALA_API_KEY", "CONTEXT_DEV_API_KEY", "VERDA_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY",
               "NVIDIA_API_KEY", "LEADLINE_LIVE_CALA")
PERSONA = {"startupName": "Smokeline", "oneLiner": "Measures and cuts Scope 3 emissions for mid-size manufacturers",
           "sector": "climate", "stage": "seed", "location": "Berlin, Germany", "region": "europe", "raiseEurM": 1.5,
           "competitors": ["Tracely"], "customers": "mid-size manufacturers"}
DEMO_PERSONA_NAME = "Carbonlens"
PENDING_STEPS = {"profile", "ranking"}
NEW_CANDIDATE = "New on Leadline, not ranked by the agent yet."
TOP_N = 10
RUN = {}  # the current run: "db" path (set by main()), "forced_failures" (jobs failed on purpose)


class SmokeFailure(AssertionError):
    pass


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def clean_env(**extra) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in SECRET_VARS}
    env["NEXT_TELEMETRY_DISABLED"] = "1"
    env.update(extra)
    return env


def schema_check(type_name: str, value) -> None:
    validator = jsonschema.Draft7Validator(json.loads((SCHEMAS / f"{type_name}.json").read_text()))
    errors = sorted(validator.iter_errors(value), key=lambda e: list(e.path))
    if errors:
        where = "/".join(str(p) for p in errors[0].path) or type_name
        raise SmokeFailure(f"not a {type_name}: {where}: {errors[0].message}")


def build_is_current() -> bool:
    build_id = FRONTEND / ".next" / "BUILD_ID"
    if not build_id.exists():
        return False
    built = build_id.stat().st_mtime
    sources = [p for d in ("src", "public") for p in (FRONTEND / d).rglob("*") if p.is_file()]
    sources += [FRONTEND / n for n in ("package.json", "next.config.ts", "tsconfig.json") if (FRONTEND / n).exists()]
    return all(p.stat().st_mtime <= built for p in sources)


def wait_for(url: str, proc: subprocess.Popen, seconds: float = 90) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise SmokeFailure(f"{url}: the process exited with code {proc.returncode}")
        try:
            if httpx.get(url, timeout=2).status_code < 500:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.3)
    raise SmokeFailure(f"{url} did not answer within {seconds:.0f}s")


class Report:
    def __init__(self):
        self.rows = []

    def check(self, group: str, name: str, fn):
        try:
            detail = fn() or ""
            self.rows.append((group, name, "OK", str(detail)))
        except Exception as e:  # one failed check never hides the others
            self.rows.append((group, name, "FAIL", f"{type(e).__name__}: {e}"))

    @property
    def failed(self) -> int:
        return sum(1 for r in self.rows if r[2] != "OK")

    def print(self, outbound: list) -> None:
        width = max([len(f"{g} {n}") for g, n, _, _ in self.rows] + [10])
        for g, n, status, detail in self.rows:
            print(f"{f'{g} {n}':<{width}}  {status:<4}  {detail[:110]}")
        print(f"\n{len(self.rows) - self.failed}/{len(self.rows)} checks OK; outbound connections: {len(outbound)}")
        for line in outbound[:10]:
            print(f"  {line}")


def expect(resp: httpx.Response, status: int = 200) -> dict:
    if resp.status_code != status:
        raise SmokeFailure(f"{resp.request.method} {resp.request.url.path}: HTTP {resp.status_code}, wanted {status}: "
                           f"{resp.text[:200]}")
    return resp.json() if resp.content else {}


def browser(web: str) -> httpx.Client:
    """A client with its own cookie jar that acts like a browser on http://127.0.0.1.

    `next start` runs with NODE_ENV=production, so the session cookie is Secure. Browsers count 127.0.0.1 as a
    secure origin and send it anyway; httpx sends Secure cookies only over https, so the hook drops the flag.
    """
    def unsecure(response: httpx.Response) -> None:
        for cookie in client.cookies.jar:
            cookie.secure = False

    client = httpx.Client(base_url=web, timeout=20, event_hooks={"response": [unsecure]})
    return client


# --- checks -------------------------------------------------------------------------------------------------------

def accounts(web: str, svc: str, r: Report) -> None:
    tag = uuid.uuid4().hex[:8]
    f_email, i_email, password = f"founder-{tag}@smoke.test", f"investor-{tag}@smoke.test", "correct horse"
    founder, investor = browser(web), browser(web)
    state = {}

    def signup_founder():
        body = expect(founder.post("/api/auth/signup", json={"role": "founder", "name": "Fay", "email": f_email,
                                                             "password": password}))
        assert body == {"role": "founder"}, body

    def me_new_founder():
        user = expect(founder.get("/api/auth/me"))["user"]
        schema_check("SessionUser", user)
        assert user["email"] == f_email and user["profile"] is None and user["founderId"] is None, user

    def onboard():
        body = expect(founder.post("/api/founders", json={"profile": PERSONA, "discoverable": True}))
        state["founderId"] = body["id"]
        user = expect(founder.get("/api/auth/me"))["user"]
        schema_check("SessionUser", user)
        schema_check("FounderProfile", user["profile"])
        assert user["founderId"] == body["id"] and user["profile"] == PERSONA and user["discoverable"] is True
        status = httpx.get(f"{svc}/profiles/founder:{body['id']}").json()["status"]
        assert status in ("building", "ready"), status  # the profile job was queued
        return f"profile job {status}"

    def signup_investor():
        expect(investor.post("/api/auth/signup", json={"role": "investor", "name": "Ivo", "email": i_email,
                                                       "password": password}))
        expect(investor.post("/api/investor-fund", json={"investor": "Smoke Capital"}))
        user = expect(investor.get("/api/auth/me"))["user"]
        schema_check("SessionUser", user)
        assert user["investorName"] == "Smoke Capital", user
        status = httpx.get(f"{svc}/profiles/investor:smoke-capital").json()["status"]
        assert status in ("building", "ready"), status
        return f"profile job {status}"

    def invite():
        intro = expect(investor.post("/api/intros", json={"founderId": state["founderId"], "note": "Hello"}))["intro"]
        schema_check("Intro", intro)
        assert intro["direction"] == "investor-to-founder" and intro["status"] == "pending", intro
        state["intro"] = intro["id"]

    def founder_sees_and_accepts():
        intros = expect(founder.get("/api/intros"))["intros"]
        for i in intros:
            schema_check("Intro", i)
        assert [i["id"] for i in intros] == [state["intro"]], intros
        wrong = investor.patch("/api/intros", json={"id": state["intro"], "status": "accepted"})
        assert wrong.status_code == 404, wrong.text  # only the recipient answers
        intro = expect(founder.patch("/api/intros", json={"id": state["intro"], "status": "accepted"}))["intro"]
        schema_check("Intro", intro)
        assert intro["status"] == "accepted"
        again = founder.patch("/api/intros", json={"id": state["intro"], "status": "passed"})
        assert again.status_code == 409 and again.json()["error"], again.text  # answered once only

    def investor_sees_email():
        intros = expect(investor.get("/api/intros"))["intros"]
        assert len(intros) == 1 and intros[0]["founder"]["email"] == f_email, intros
        schema_check("Intro", {k: v for k, v in intros[0].items() if k != "founder"})

    def founder_requests_intro():
        intro = expect(founder.post("/api/intros", json={"investor": "Smoke Capital", "note": "Hi"}))["intro"]
        schema_check("Intro", intro)
        assert intro["direction"] == "founder-to-investor"
        again = expect(founder.post("/api/intros", json={"investor": "Smoke Capital", "note": "Hi"}))["intro"]
        assert again["id"] == intro["id"]  # a pending duplicate is returned

    def logout_login():
        expect(founder.post("/api/auth/logout"))
        assert expect(founder.get("/api/auth/me"))["user"] is None
        bad = founder.post("/api/auth/login", json={"email": f_email, "password": "wrong password"})
        assert bad.status_code == 401, bad.text
        assert expect(founder.post("/api/auth/login", json={"email": f_email, "password": password})) == \
            {"role": "founder"}
        assert expect(founder.get("/api/auth/me"))["user"]["founderId"] == state["founderId"]

    def duplicate_signup():
        dup = httpx.post(f"{web}/api/auth/signup", json={"role": "founder", "name": "X", "email": f_email,
                                                         "password": password})
        assert dup.status_code == 409 and dup.json()["error"], dup.text

    def demo_logins():
        demo = browser(web)
        assert expect(demo.post("/api/auth/demo", json={"role": "founder"})) == {"role": "founder"}
        user = expect(demo.get("/api/auth/me"))["user"]
        schema_check("SessionUser", user)
        assert user["profile"]["startupName"] == DEMO_PERSONA_NAME and user["discoverable"] is True, user
        first = user["id"]
        demo2 = browser(web)
        expect(demo2.post("/api/auth/demo", json={"role": "founder"}))
        assert expect(demo2.get("/api/auth/me"))["user"]["id"] == first  # made once
        inv = browser(web)
        expect(inv.post("/api/auth/demo", json={"role": "investor"}))
        assert expect(inv.get("/api/auth/me"))["user"]["investorName"] == "Fjord Ventures"

    for name, fn in [("POST /api/auth/signup (founder)", signup_founder), ("GET /api/auth/me", me_new_founder),
                     ("POST /api/founders (onboarding)", onboard),
                     ("POST /api/auth/signup + /api/investor-fund", signup_investor),
                     ("POST /api/intros (investor invites)", invite),
                     ("GET+PATCH /api/intros (founder accepts)", founder_sees_and_accepts),
                     ("GET /api/intros (investor, email shown)", investor_sees_email),
                     ("POST /api/intros (founder asks, dedup)", founder_requests_intro),
                     ("POST /api/auth/logout + login", logout_login),
                     ("POST /api/auth/signup (duplicate)", duplicate_signup),
                     ("POST /api/auth/demo (both roles)", demo_logins)]:
        r.check("accounts", name, fn)


def poll_shortlist(client: httpx.Client, profile: dict, seconds: float = 180) -> tuple[dict, list, list]:
    """POST /api/shortlist until ready; intermediate answers must name the active build step."""
    codes, steps, deadline = [], [], time.monotonic() + seconds
    while True:
        resp = client.post("/api/shortlist", json=profile)
        codes.append(resp.status_code)
        if resp.status_code == 200:
            return resp.json(), codes, steps
        pending = resp.json()
        if resp.status_code != 202 or pending.get("status") != "building" or pending.get("step") not in PENDING_STEPS:
            raise SmokeFailure(f"shortlist: HTTP {resp.status_code}: {resp.text[:200]}")
        schema_check("ShortlistPending", pending)
        steps.append(pending["step"])
        if time.monotonic() > deadline:
            raise SmokeFailure(f"shortlist still building after {seconds:.0f}s")
        time.sleep(0.5)


def wait_idle(svc: str, seconds: float = 240) -> dict:
    """Wait until the service worker has no queued or running job."""
    deadline = time.monotonic() + seconds
    while True:
        jobs = httpx.get(f"{svc}/status", timeout=10).json()["jobs"]
        if not jobs["queued"] and not jobs["running"]:
            return jobs
        if time.monotonic() > deadline:
            raise SmokeFailure(f"jobs still pending after {seconds:.0f}s: {jobs}")
        time.sleep(0.5)


def without(d: dict, *keys) -> dict:
    return {k: v for k, v in d.items() if k not in keys}


def data(web: str, svc: str, r: Report) -> None:
    tag = uuid.uuid4().hex[:8]
    state = {}
    fresh, founder, investor = browser(web), browser(web), browser(web)

    def failed_profile_is_reported():
        # The seeded jobs are still queued ahead, so this founder's profile job is waiting; mark it failed.
        client = browser(web)
        expect(client.post("/api/auth/signup", json={"role": "founder", "name": "Fen", "email": f"fail-{tag}@smoke.test",
                                                     "password": "correct horse"}))
        founder_id = expect(client.post("/api/founders", json={"profile": PERSONA, "discoverable": False}))["id"]
        with sqlite3.connect(RUN["db"], timeout=10) as db:
            n = db.execute("UPDATE jobs SET status = 'failed', error = 'smoke: forced failure', finished_at = "
                           "strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE kind = 'profile' AND subject_key = ? AND "
                           "status = 'queued'", (f"founder:{founder_id}",)).rowcount
        assert n == 1, "the profile job was no longer queued (the worker was too quick)"
        RUN["forced_failures"] = RUN.get("forced_failures", 0) + 1
        failed = client.post("/api/shortlist", json=PERSONA)
        assert failed.status_code == 502 and "Save your profile again" in failed.json()["error"], failed.text
        expect(client.post("/api/founders", json={"profile": PERSONA, "discoverable": False}))  # retry
        again = client.post("/api/shortlist", json=PERSONA)
        assert again.status_code in (200, 202), again.text
        return f"502 \"{failed.json()['error'][:48]}...\", then {again.status_code} after saving again"

    def new_founder_waits_for_ranking():
        # Right after start the seeded profile jobs are queued ahead of this one, so the ranking is still building.
        expect(fresh.post("/api/auth/signup", json={"role": "founder", "name": "Nia", "email": f"new-{tag}@smoke.test",
                                                    "password": "correct horse"}))
        expect(fresh.post("/api/founders", json={"profile": PERSONA, "discoverable": True}))
        body, codes, steps = poll_shortlist(fresh, PERSONA)
        # Usually 202 (profile, then ranking) first; a fast worker may finish a step before the first poll.
        assert codes[0] in (200, 202), f"the first answer was {codes[0]}"
        assert steps == sorted(steps, key=["profile", "ranking"].index), f"steps went backwards: {steps}"
        schema_check("ShortlistResponse", body)
        ranked = [i for i in body["investors"] if i["explanation"] != NEW_CANDIDATE]
        assert 0 < len(ranked) <= TOP_N, f"{len(ranked)} ranked investors"
        return f"{len(steps)} pending updates ({steps[0]} first) then ready; {len(ranked)} ranked, {len(body['investors']) - len(ranked)} new"

    def failed_rank_can_be_retried():
        # A founder whose profile is stored but whose ranking failed: the shortlist says how to retry, and saving
        # the profile again queues one new rank job (the shortlist then reports the ranking step as building).
        client = browser(web)
        expect(client.post("/api/auth/signup", json={"role": "founder", "name": "Ria", "email": f"rank-{tag}@smoke.test",
                                                     "password": "correct horse"}))
        founder_id = expect(client.post("/api/founders", json={"profile": PERSONA, "discoverable": False}))["id"]
        key = f"founder:{founder_id}"
        wait_idle(svc)  # its profile and first ranking are built; now make the ranking look failed
        now = datetime.now(timezone.utc).isoformat()  # the database's own format, so job order stays true
        with sqlite3.connect(RUN["db"], timeout=10) as db:
            assert db.execute("SELECT 1 FROM profiles WHERE key = ?", (key,)).fetchone(), "no stored profile"
            db.execute("DELETE FROM rankings WHERE subject_key = ?", (key,))
            db.execute("INSERT INTO jobs (id, kind, subject_key, status, attempts, error, created_at, finished_at) "
                       "VALUES (?, 'rank', ?, 'failed', 1, 'smoke: forced rank failure', ?, ?)",
                       (uuid.uuid4().hex, key, now, now))
        RUN["forced_failures"] = RUN.get("forced_failures", 0) + 1
        failed = client.post("/api/shortlist", json=PERSONA)
        assert failed.status_code == 502 and "Save your profile again" in failed.json()["error"], failed.text
        expect(client.post("/api/founders", json={"profile": PERSONA, "discoverable": False}))  # retry
        again = client.post("/api/shortlist", json=PERSONA)
        assert again.status_code in (200, 202), again.text
        if again.status_code == 202:
            assert again.json()["step"] == "ranking", again.text
        return f"502 \"{failed.json()['error'][:48]}...\", then {again.status_code} after saving again"

    def jobs_finish():
        jobs = wait_idle(svc)
        assert jobs["failed"] == RUN.get("forced_failures", 0), jobs  # only the job failed on purpose above
        return f"jobs {jobs}"

    def demo_founder_shortlist():
        expect(founder.post("/api/auth/demo", json={"role": "founder"}))
        user = expect(founder.get("/api/auth/me"))["user"]
        state["profile"], state["founderId"] = user["profile"], user["founderId"]
        body, _, _ = poll_shortlist(founder, state["profile"])
        schema_check("ShortlistResponse", body)
        assert body["investors"], "no investors"
        state["investors"] = body["investors"]
        return f"{len(body['investors'])} investors, {body['roundsAnalysed']} rounds, mode {body['mode']}"

    def investor_brief():
        tried = []
        for inv in state["investors"]:
            resp = founder.post("/api/investor", json={"profile": state["profile"], "slug": inv["slug"]})
            tried.append(resp.status_code)
            if resp.status_code == 200:
                body = resp.json()
                schema_check("InvestorBrief", without(body, "mode"))
                return f"{inv['name']} (rank {body['rank']} of {body['of']})"
            if resp.status_code != 404:
                raise SmokeFailure(f"HTTP {resp.status_code}: {resp.text[:200]}")
        raise SmokeFailure(f"no shortlisted investor has a brief (statuses {tried})")

    def fit_uses_agent_score():
        top = next(i for i in state["investors"] if i["explanation"] != NEW_CANDIDATE)
        body = expect(founder.post("/api/fit", json={"profile": state["profile"], "investor": top["name"]}))
        schema_check("FitReport", body)
        assert body["score"] == top["score"], (body["score"], top["score"])
        return f"{top['name']}: {body['score']}"

    def twins():
        body = expect(founder.post("/api/twins", json=state["profile"]))
        schema_check("TwinsResponse", body)
        return f"{len(body['twins'])} twins"

    def signals():
        body = expect(founder.post("/api/signals", json=state["profile"]))
        schema_check("SignalsResponse", body)
        return f"{len(body['signals'])} signals"

    def funds():
        name = state["investors"][0]["name"]
        body = expect(founder.get("/api/funds", params={"q": name[:4]}))
        assert any(f["name"] == name for f in body["funds"]), body
        for f in body["funds"]:
            assert set(f) == {"id", "name"}, f
        return f"{len(body['funds'])} for {name[:4]!r}"

    def status():
        body = expect(founder.get("/api/status"))
        assert body["mode"] in ("live", "simulated") and set(body["jobs"]) == {"queued", "running", "failed"}, body
        return f"mode {body['mode']}"

    def discover():
        expect(investor.post("/api/auth/demo", json={"role": "investor"}))
        body = expect(investor.post("/api/discover", json={}))
        schema_check("DiscoverResponse", body)
        return f"{len(body['founders'])} founders, {len(body['nextTwins'])} next twins"

    def thesis():
        name = state["investors"][0]["name"]
        body = expect(investor.post("/api/thesis", json={"investor": name}))
        schema_check("InvestorThesis", body)
        return f"{name}: led {body['roundsLed']}, joined {body['roundsJoined']}"

    def company():
        deal = httpx.get(f"{svc}/deals", timeout=10).json()[0]
        body = expect(investor.post("/api/company", json={"company": deal["company"]}))
        schema_check("CompanyDiligence", body)
        return deal["company"]

    def startup():
        body = expect(investor.post("/api/startup", json={"founderId": state["founderId"]}))
        schema_check("StartupDiligence", body)
        assert isinstance(body["fit"]["score"], int) and 0 <= body["fit"]["score"] <= 100, body.get("fit")
        return f"fit {body['fit']['score']}"

    for name, fn in [("POST /api/shortlist (failed profile build)", failed_profile_is_reported),
                     ("POST /api/shortlist (new founder: 202, then 200)", new_founder_waits_for_ranking),
                     ("POST /api/shortlist (failed ranking, then retry)", failed_rank_can_be_retried),
                     ("worker: every queued job finished", jobs_finish),
                     ("POST /api/shortlist (demo founder)", demo_founder_shortlist),
                     ("POST /api/investor", investor_brief), ("POST /api/fit (agent score)", fit_uses_agent_score),
                     ("POST /api/twins", twins), ("POST /api/signals", signals), ("GET /api/funds", funds),
                     ("GET /api/status", status), ("POST /api/discover", discover), ("POST /api/thesis", thesis),
                     ("POST /api/company", company), ("POST /api/startup", startup)]:
        r.check("data", name, fn)


def service_down(web: str, r: Report) -> None:
    """Run after the service is stopped: the routes answer the UI's JSON errors."""
    client = browser(web)
    client.cookies.set("leadline_session", "smoke-token")  # any session makes the route ask the service

    def me():
        resp = client.get("/api/auth/me")
        assert resp.status_code == 503 and "not reachable" in resp.json()["error"], resp.text

    def shortlist():
        resp = client.post("/api/shortlist", json=PERSONA)
        assert resp.status_code == 503 and resp.json()["error"], resp.text

    def status():
        body = expect(client.get("/api/status"))
        assert body["mode"] in ("live", "simulated") and body["error"], body

    for name, fn in [("GET /api/auth/me", me), ("POST /api/shortlist", shortlist), ("GET /api/status", status)]:
        r.check("service down", name, fn)


# "data" runs first: its failed-profile and first-503 checks need the seeded jobs still queued ahead of theirs.
GROUPS = {"data": data, "accounts": accounts}


# --- run ----------------------------------------------------------------------------------------------------------

def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--only", choices=[*GROUPS, "all"], default="all")
    p.add_argument("--no-build", action="store_true", help="use the existing .next build as it is")
    p.add_argument("--keep", action="store_true", help="keep the temp directory (DB, logs)")
    args = p.parse_args(argv)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))  # a terminated run still stops its servers (finally)

    if not args.no_build and not build_is_current():
        print("building the frontend (next build) ...", flush=True)
        subprocess.run(["npm", "run", "build"], cwd=FRONTEND, check=True, env=clean_env(),
                       stdout=subprocess.DEVNULL)

    tmp = Path(tempfile.mkdtemp(prefix="leadline-smoke-"))
    outbound_log = tmp / "outbound.log"
    outbound_log.touch()
    svc_port, web_port = free_port(), free_port()
    svc, web = f"http://127.0.0.1:{svc_port}", f"http://127.0.0.1:{web_port}"
    RUN.clear()
    RUN["db"] = str(tmp / "leadline.db")
    procs = []
    report = Report()
    try:
        py_env = clean_env(PYTHONPATH=str(PY_GUARD), SMOKE_OUTBOUND_LOG=str(outbound_log))
        seed = subprocess.run([str(PYTHON), str(ROOT / "scripts" / "seed_db.py"), "--db", str(tmp / "leadline.db")],
                              cwd=ROOT, env=py_env, capture_output=True, text=True)
        (tmp / "seed.log").write_text(seed.stdout + seed.stderr)
        if seed.returncode != 0:
            raise SmokeFailure(f"seed_db.py exited {seed.returncode}: {(seed.stderr or seed.stdout)[-300:]}")
        procs.append(subprocess.Popen(
            [str(PYTHON), str(ROOT / "leadline" / "serve.py"), "--db", str(tmp / "leadline.db"), "--port",
             str(svc_port), "--fake-model"], cwd=ROOT, env=py_env, stdout=open(tmp / "service.log", "w"),
            stderr=subprocess.STDOUT))
        procs.append(subprocess.Popen(
            [str(FRONTEND / "node_modules" / ".bin" / "next"), "start", "-p", str(web_port), "-H", "127.0.0.1"],
            cwd=FRONTEND, stdout=open(tmp / "next.log", "w"), stderr=subprocess.STDOUT,
            env=clean_env(LEADLINE_SERVICE_URL=svc, LEADLINE_DEMO_LOGIN="true", SMOKE_OUTBOUND_LOG=str(outbound_log),
                          NODE_OPTIONS=f"--require {GUARD}")))
        wait_for(f"{svc}/status", procs[0])
        wait_for(f"{web}/api/auth/me", procs[1])
        for name, group in GROUPS.items():
            if args.only in (name, "all"):
                group(web, svc, report)
        procs[0].terminate()
        procs[0].wait(10)
        service_down(web, report)
    except SmokeFailure as e:
        report.rows.append(("setup", "start", "FAIL", str(e)))
    finally:
        for proc in procs:
            proc.terminate()
        for proc in procs:
            try:
                proc.wait(10)
            except subprocess.TimeoutExpired:
                proc.kill()
    outbound = [line for line in outbound_log.read_text().splitlines() if line]
    if outbound:
        report.rows.append(("guard", "no outbound connections", "FAIL", f"{len(outbound)} blocked"))
    report.print(outbound)
    if args.keep or report.failed:
        print(f"logs and DB kept in {tmp}")
    else:
        shutil.rmtree(tmp, ignore_errors=True)
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())
