"""Background jobs for the Leadline service.

One `Worker` thread takes jobs from `LeadlineDb` (table `jobs`) one at a time and runs the handler for the job's kind:

    profile_agent, match_agent = make_agents()
    worker = Worker(db, handlers(profile_agent, match_agent))
    worker.start()

A handler returns a dict (optional `trace_id` and `usage`, logged) or raises `JobFailed`; any other exception also
fails the job, with its type in the error, and the worker goes on. The profile job builds a user's profile with the
`leadline-profile` plugin, stores it as a new version and queues one rank job for that user (no other user is
re-ranked). The rank job ranks that user against the other side's stored profiles: the best N by fit go to
the leadline-match agent, and the result is stored as a new ranking."""
from __future__ import annotations

import logging
import os
import threading
import time
import uuid

from ranking import candidate_pool
from runtime import AgentBridge, load_agent
from shapes import founder_profile_input, investor_profile_input, slugify

log = logging.getLogger("leadline.jobs")

STALE_AFTER_S = 1800  # a job running longer than this was left by a stopped worker (a profile build takes minutes)
FINISH_TRIES, FINISH_RETRY_S = 3, 1.0  # finish_job is retried when the database is busy


class JobFailed(Exception):
    """A job failed for a known reason; `str(e)` is stored as the job's error."""

    def __init__(self, message: str, trace_id: str | None = None):
        super().__init__(message)
        self.trace_id = trace_id


def make_agents(environ=None, agent_root=None, model=None):
    """(profile agent, match agent) from the injected agent.

    Profile agent: Context.dev web tools when CONTEXT_DEV_API_KEY is set (the agent reads it); Cala only when
    LEADLINE_LIVE_CALA=1, so no credit is spent by accident (cap per run: VENUS_CALA_MAX_CALLS, default 3).
    Match agent: no web tools and no Cala; the rank job works from stored profiles only.
    `model` (tests, --fake-model) replaces the base model of both."""
    env = os.environ if environ is None else environ
    common = {"environ": env}
    if model is not None:
        common["model"] = model
    profile = load_agent(agent_root, cala=env.get("LEADLINE_LIVE_CALA") == "1", **common)
    match = load_agent(agent_root, cala=False, web_tools=[], **common)
    return profile, match


def profile_input(db, key: str) -> dict:
    """The leadline-profile input for a profile key, from the DB: `founder:<id>` -> that founder record and its
    company's rounds; `investor:<slug>` -> the fund an investor user named, and the rounds it is in."""
    kind, _, ident = key.partition(":")
    if kind == "founder" and ident:
        record = db.founder(ident)
        if record is None:
            raise JobFailed(f"no founder record {ident!r}")
        company = (record.get("profile") or {}).get("startupName")
        return founder_profile_input(record, db.rounds(company=company) if company else [])
    if kind == "investor" and ident:
        name = next((n for n in db.investor_names() if slugify(n) == ident), None)
        if name is None:
            raise JobFailed(f"no investor user with a fund named like {ident!r}")
        return investor_profile_input(name, db.rounds(investor=name))
    raise JobFailed(f"unknown profile key {key!r} (expected founder:<id> or investor:<slug>)")


def run_profile_job(db, agent, job: dict) -> dict:
    """Build and store one user's profile, then queue the rank job for that user."""
    key = job["subject_key"]
    payload = profile_input(db, key)
    trace = job.get("trace_id") or uuid.uuid4().hex  # the Cala hook stores every reply of this run under it
    resp = AgentBridge(db, agent).run("leadline-profile", payload, trace_id=trace)
    trace = resp.get("trace_id") or trace
    if resp.get("status") != "ok":
        err = resp.get("error") or {}
        raise JobFailed(f"{err.get('code', 'run_failed')}: {err.get('message', 'no message')}", trace)
    out = resp["outputs"][0]["output"]
    version = db.put(key, out["profile"], out["rating"], out.get("changes") or [])
    db.enqueue_job("rank", key)
    return {"trace_id": trace, "version": version, "usage": resp.get("usage") or {},
            "base_model": resp.get("base_model"), "warnings": resp.get("warnings") or []}


def run_rank_job(db, agent, job: dict) -> dict:
    """Rank one user against the other side's stored profiles (no Cala, no web) and store the ranking. With no
    candidate left after the prefilter, an empty ranking is stored without a model call."""
    key = job["subject_key"]
    subject = db.get(key)
    if subject is None:
        raise JobFailed(f"no stored profile for {key!r}; the profile job must finish first")
    pool = candidate_pool(db, key)
    versions = {r["key"]: r["version"] for r in pool}
    trace = job.get("trace_id") or uuid.uuid4().hex
    resp = AgentBridge(db, agent).rank(subject, pool, trace_id=trace)
    trace = resp.get("trace_id") or trace
    if resp.get("status") != "ok":
        err = resp.get("error") or {}
        raise JobFailed(f"{err.get('code', 'run_failed')}: {err.get('message', 'no message')}", trace)
    out = resp["outputs"][0]["output"]
    payload = {"matches": out.get("matches") or [],
               "rejected": (out.get("rejected") or []) + resp["prefilter_rejected"],
               "evidence": out.get("evidence") or [], "warnings": (out.get("warnings") or []) + (resp.get("warnings") or []),
               "stats": out.get("stats") or {}, "selected": resp["selected"], "settings": resp["settings"],
               "top_n": resp["top_n"], "unseen": resp.get("unseen") or [], "strategy": resp.get("strategy"), "base_model": resp.get("base_model")}
    candidates = [{"key": k, "version": versions[k]} for k, _ in resp["selected"]]
    db.put_ranking(key, subject["version"], candidates, payload, trace)
    return {"trace_id": trace, "usage": resp.get("usage") or {}, "base_model": resp.get("base_model")}


def handlers(profile_agent, match_agent) -> dict:
    """The worker's job handlers: profile jobs use the profile agent, rank jobs the match agent."""
    return {"profile": lambda db, job: run_profile_job(db, profile_agent, job),
            "rank": lambda db, job: run_rank_job(db, match_agent, job)}


class Worker:
    def __init__(self, db, handlers: dict, *, poll_s: float = 1.0, stale_after_s: float = STALE_AFTER_S):
        self.db, self.handlers = db, dict(handlers)
        self.poll_s, self.stale_after_s = poll_s, stale_after_s
        self._stop = threading.Event()
        self._thread = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def recover(self) -> int:
        """Queue again the jobs a stopped worker left running (or fail them after 2 attempts)."""
        return self.db.requeue_stale(self.stale_after_s)

    def run_once(self) -> dict | None:
        """Claim and run one job; returns the finished job row, or None when the queue is empty."""
        job = self.db.claim_job()
        if job is None:
            return None
        start = time.monotonic()
        job = {**job, "trace_id": uuid.uuid4().hex}  # set here so a crash still records which run it was
        handler = self.handlers.get(job["kind"])
        result, error, trace = {}, None, job["trace_id"]
        if handler is None:
            error = f"no handler for {job['kind']} jobs"
        else:
            try:
                result = handler(self.db, job) or {}
                trace = result.get("trace_id") or trace
            except JobFailed as e:
                error, trace = str(e), e.trace_id
            except Exception as e:  # a bug: fail this job, keep the worker alive, keep the traceback in the log
                log.exception("job %s %s crashed", job["kind"], job["subject_key"])
                error = f"{type(e).__name__}: {e}"
        if not self._finish(job, error, trace):
            log.warning("job %s %s: attempt %s finished after it was requeued; result dropped", job["kind"],
                        job["subject_key"], job["attempts"])
        usage, model = result.get("usage") or {}, result.get("base_model") or {}
        log.info("job kind=%s key=%s status=%s model_calls=%s web_calls=%s cala_calls=%s seconds=%.1f model=%s%s",
                 job["kind"], job["subject_key"], "failed" if error else "done", usage.get("model_calls", 0),
                 usage.get("web_calls", 0), usage.get("cala_calls", 0), time.monotonic() - start,
                 f"{model.get('provider')}/{model.get('model')}" if model else "-", f" error={error}" if error else "")
        return self.db.job(job["id"])

    def _finish(self, job, error, trace) -> bool:
        for i in range(FINISH_TRIES):
            try:
                return self.db.finish_job(job["id"], error=error, trace_id=trace, attempt=job["attempts"])
            except Exception:
                if i + 1 == FINISH_TRIES:
                    raise  # the job stays running; requeue_stale picks it up
                log.warning("finish_job for %s %s failed; retrying", job["kind"], job["subject_key"], exc_info=True)
                time.sleep(FINISH_RETRY_S)

    def start(self) -> None:
        """Start the worker thread. One worker per database is assumed: jobs left running by a stopped process are
        queued again at once (or failed after 2 attempts). After a stop() that timed out mid-job, the same thread
        just carries on."""
        if self.running:
            self._stop.clear()
            return
        self.db.requeue_stale(0)
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="leadline-worker", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 10) -> None:
        """Stop after the current job (a model call in flight is not cut off)."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                job = self.run_once()
            except Exception:  # e.g. the database was locked too long: wait and try again
                log.exception("worker loop error")
                job = None
            if job is None:
                self._stop.wait(self.poll_s)
