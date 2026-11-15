"""Top-N selection from stored profiles, and the check that a stored ranking is out of date.

A user is ranked against the other side's stored profiles only (no Cala, no web): the trained prefilter drops clear
clashes, the rest are sorted by `fit_score`, then by their rating, and the best N (LEADLINE_TOP_N, default 10) go to
the leadline-match agent. Nobody else is re-ranked when a profile changes; instead `needs_rerank` tells the page load
when this user's best N changed, so one rank job can be queued for them."""
from __future__ import annotations

import json
import os

from db import PROFILE_PREFIX
from runtime import _configured_prefilter

TOP_N = int(os.environ.get("LEADLINE_TOP_N", 10))
FIT_WEIGHTS = {"sector": 0.4, "stage": 0.25, "region": 0.2, "check_size": 0.15}  # a guess; change here only
UNKNOWN = 0.5  # half credit when either side doesn't state the fact: above any known mismatch, below a match
GENERALIST_FIT = 0.75  # a generalist fits every sector, less sharply than a stated match
NEXT_STAGE_FIT = 0.25  # one stage apart (the prefilter keeps it): a weak fit, still below unknown
LEAD_CHECK_SHARE = 0.2  # a check that is at least this share of the round can lead it

_pf = None
_by_settings = {}  # json of the settings -> the prefilter module configured with them (loaded once each)


def _prefilter():
    """The prefilter module with its default settings: its word tables and parsers score the fit too."""
    global _pf
    if _pf is None:
        _pf = _configured_prefilter({})
    return _pf


def _prefilter_for(settings: dict):
    key = json.dumps(settings or {}, sort_keys=True)
    if key not in _by_settings:
        _by_settings[key] = _configured_prefilter(settings or {})
    return _by_settings[key]


def _sides(subject: dict, candidate: dict):
    return (subject, candidate) if subject.get("kind") == "startup" else (candidate, subject)


def _sector_part(pf, s, i) -> float:
    mine, theirs = pf._sector_terms(s.get("sectors")), pf._sector_terms(i.get("sectors"))
    if not mine or not theirs:
        return UNKNOWN
    if pf.GENERALIST & (mine | theirs):
        return GENERALIST_FIT
    return sum(any(pf._sectors_fit(a, b) for b in theirs) for a in mine) / len(mine)


def _stage_part(pf, s, i) -> float:
    mine = pf._stage(s["stage"]) if s.get("stage") else None
    parsed = [pf._stage(x) for x in i.get("stages") or []]
    theirs = [t for t in parsed if t]
    if mine is None or not parsed:
        return UNKNOWN
    if mine in theirs:
        return 1.0
    if None in parsed or not theirs:
        return UNKNOWN  # a stage name we can't place might be the startup's
    steps = min(abs(pf.STAGES[mine] - pf.STAGES[t]) for t in theirs)
    return NEXT_STAGE_FIT if steps == 1 else 0.0


def _region_part(pf, s, i) -> float:
    country = pf._place(s["country"]) if s.get("country") else None
    regions = [pf._place(r) for r in i.get("regions") or [] if r]
    if country not in pf.COUNTRIES or not regions:
        return UNKNOWN
    if any(r in pf.GLOBAL or r == country or country in pf.REGION_GROUPS.get(r, ()) for r in regions):
        return 1.0
    if any(r not in pf.REGION_GROUPS and r not in pf.COUNTRIES for r in regions):
        return UNKNOWN  # a name we can't place might cover the country
    return 0.0


def _check_part(pf, s, i) -> float:
    raising, check = s.get("raising") or {}, i.get("check_size") or {}
    amount, low, high = pf._num(raising.get("amount")), pf._num(check.get("min")), pf._num(check.get("max"))
    cur_a, cur_c = raising.get("currency"), check.get("currency")
    if amount is None or (low is None and high is None) or not cur_a or not cur_c or pf._word(cur_a) != pf._word(cur_c):
        return UNKNOWN
    if low is not None and high is not None and low > high:
        return UNKNOWN
    fits = (low is None or low <= amount) and (high is None or high >= amount * LEAD_CHECK_SHARE)
    return 1.0 if fits else 0.0


PARTS = {"sector": _sector_part, "stage": _stage_part, "region": _region_part, "check_size": _check_part}


def fit_parts(subject: dict, candidate: dict) -> dict:
    pf, (s, i) = _prefilter(), _sides(subject, candidate)
    out = {}
    for name, part in PARTS.items():
        try:
            out[name] = part(pf, s, i)
        except Exception:  # odd data counts as unknown, like the prefilter
            out[name] = UNKNOWN
    return out


def fit_score(subject: dict, candidate: dict) -> float:
    """How well a startup and an investor fit on stated facts, in [0, 1]; either one can be the subject."""
    parts = fit_parts(subject, candidate)
    return round(sum(FIT_WEIGHTS[k] * parts[k] for k in FIT_WEIGHTS), 6)


def match_profile(record: dict) -> dict:
    """A stored profile record ({key, version, profile, rating}) -> a leadline-match profile: the key as id, the
    rating's total and parts, without the per-field `sources` map (the match agent cites facts, not that map)."""
    profile = {k: v for k, v in (record.get("profile") or {}).items() if k != "sources"}
    profile["id"] = record["key"]
    rating = record.get("rating") or {}
    if "total" in rating:
        profile["rating"] = {"total": rating["total"], "parts": dict(rating.get("parts") or {})}
    return profile


def direction_for(subject: dict) -> str:
    return "startup_to_investors" if subject.get("kind") == "startup" else "investor_to_startups"


def select_top_n(subject: dict, candidates: list, settings: dict, n: int = TOP_N) -> dict:
    """Prefilter (the trained `settings`: same rules, so a clash is never selected), then the best `n` by
    (fit_score, rating.total), ties by id. Returns {selected: [[key, fit]], rejected: [{candidate_id, reason,
    detail}]}; both sides are match profiles."""
    pf = _prefilter_for(settings)
    want = "investor" if subject.get("kind") == "startup" else "startup"
    rejected, scored, seen = [], [], set()
    for c in candidates:
        cid = c.get("id")
        if cid == subject.get("id") or cid in seen or c.get("kind") != want:
            continue
        seen.add(cid)
        s, i = _sides(subject, c)
        clash = pf._first_clash(s, i)
        if clash:
            rejected.append({"candidate_id": cid, "reason": clash[0], "detail": clash[1]})
            continue
        total = (c.get("rating") or {}).get("total") or 0
        scored.append((fit_score(subject, c), total, cid))
    scored.sort(key=lambda t: (-t[0], -t[1], t[2]))
    return {"selected": [[cid, fit] for fit, _, cid in scored[:max(0, int(n))]], "rejected": rejected}


def subject_kind(key: str) -> str:
    for kind, prefix in PROFILE_PREFIX.items():
        if key.startswith(prefix):
            return kind
    raise ValueError(f"not a user profile key: {key!r}")


def candidate_pool(db, key: str) -> list:
    """The other side's newest stored profiles: every investor for a startup; for an investor, the startups whose
    founder chose to be discoverable."""
    other = "investor" if subject_kind(key) == "startup" else "startup"
    pool = [r for r in db.latest_profiles(other) if r["key"] != key]
    if other == "startup":
        shown = {f"{PROFILE_PREFIX['startup']}{f['id']}" for f in db.discoverable_founders()}
        pool = [r for r in pool if r["key"] in shown]
    return pool


def needs_rerank(db, key: str) -> bool:
    """True when this user's stored ranking is out of date: none yet (with a profile to rank), the user's profile
    changed, the best N (same settings as that ranking) is a different set, or a selected candidate's profile has a
    newer version. False while a rank job is queued or running (the profile job queues one for a changed subject),
    and after the newest rank job failed, so page loads don't keep retrying a failing model; the next profile job
    queues a fresh one. Reads only; the caller queues the rank job."""
    subject = db.get(key)
    if subject is None:
        return False
    latest = db.latest_ranking(key)
    job = db.job_state("rank", key)
    if job is not None and (job["status"] in ("queued", "running") or
                            job["status"] == "failed" and (latest is None or job["created_at"] >= latest["created_at"])):
        return False
    if latest is None:
        return True
    if subject["version"] != latest["subject_version"]:
        return True
    selected, pool = current_top(db, key, subject, latest.get("payload"))
    chosen = {k for k, _ in selected}
    stored = {c["key"]: c["version"] for c in latest.get("candidates") or []}
    offered = set(stored) | set((latest.get("payload") or {}).get("unseen") or [])  # cut for size: still offered
    return chosen != offered or any(pool[k]["version"] != stored[k] for k in chosen & set(stored))


def current_top(db, key: str, subject: dict, payload: dict | None = None):
    """The best N for this user right now, with the settings and N a stored ranking (`payload`) was made with:
    (selected [[key, fit]], {key: candidate record})."""
    payload = payload or {}
    pool = {r["key"]: r for r in candidate_pool(db, key)}
    top = select_top_n(match_profile(subject), [match_profile(r) for r in pool.values()],
                       payload.get("settings") or {}, n=payload.get("top_n") or TOP_N)
    return top["selected"], pool
