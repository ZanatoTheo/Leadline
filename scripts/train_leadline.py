"""Train the Leadline agents (leadline-match on Cala time-split cases, leadline-profile on per-company cases), in
process, and promote the drafts that pass.

    venus/.venv/bin/python scripts/train_leadline.py --dry-run          # what a run would spend, no model calls
    venus/.venv/bin/python scripts/train_leadline.py --cases 2           # train on 2 cases
    venus/.venv/bin/python scripts/train_leadline.py --refresh --dry-run # fetch the Cala pull if not cached
    venus/.venv/bin/python scripts/train_leadline.py --plugin both --promote --profile-db leadline/data/leadline.db

Steps: Cala rows from the app's disk cache (`app/data/cache`; Cala is called only with --refresh, at most
--max-cala-calls times, checked before any call) -> `leadline/build_cases.py` (time-split cases, prefilter applied)
-> Venus training (`check_request` + `train`, the same path as `Venus.handle`, with per-case limits) -> a draft
strategy in --strategies. Prints one JSON ledger: Cala calls and cache hits, model calls, web tool calls, real web
HTTP calls, tokens, scores. Exit codes: 0 done, 1 training failed, 2 Cala stop (not cached / over the cap),
3 no case (no row names a lead), 4 broken training model config (checked before any call), 5 --promote refused a
draft (reasons in the ledger).

--plugin both trains leadline-profile first, then leadline-match. --profile-db builds each match subject's profile
with leadline-profile (no web tools; the promoted profile strategy's tendencies if there is one) into a LeadlineDb,
reusing stored profiles. --promote gates each draft (venus.gate, free), refuses it when its mean score is under
--min-score or a tendency names a training answer (a subject, or a lead the case hides), and otherwise writes
<plugin>-default.json with status "validated" and the trace id, scores and gate metrics in `notes`. Without a draft
(no web research) the plugin's seed tendencies are what gets promoted.

Web pages (Context.dev) and model replies are cached under VENUS_CACHE_DIR (default `.venus_cache` at the repo root),
so a rerun of the same cases spends nothing (training search results never expire and scrapes are never forced
fresh); --no-model-cache asks the model again. In the match run, web calls that name a match subject are refused
(answer-leak guard, `guard_tools`): the web knows who led a round the case hides. The profile run may look up its
own company: that is the profile task.
"""
import hashlib
import argparse
import json
import os
from datetime import datetime, timezone
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "app", ROOT / "venus", ROOT / "leadline"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import httpx  # noqa: E402

from build_cases import LEAD_RULES, CaseError, build_cases, build_profile_cases, load_rows  # noqa: E402
from db import LeadlineDb  # noqa: E402
from profiles import case_runner  # noqa: E402
from venus.cache import cache_from_env  # noqa: E402
from venus.config import resolve_model  # noqa: E402
from venus.envfile import load_env  # noqa: E402
from venus.errors import VenusError  # noqa: E402
from venus.gate import gate  # noqa: E402
from venus.plugin import load_plugins  # noqa: E402
from venus.request import VENUS_VERSION, check_request  # noqa: E402
from venus.runner import MAX_WEB_CALLS  # noqa: E402
from venus.schemas import load_schema  # noqa: E402
from venus.serve import default_model_factory, training_base_model  # noqa: E402
from venus.tools import Tool  # noqa: E402
from venus.strategy import Strategy, StrategyStore  # noqa: E402
from venus.training import TRAIN_CASE_LIMITS, train  # noqa: E402
from venus.web import ContextDev, key_from_env, web_tools  # noqa: E402

PLUGINS = ("leadline-profile", "leadline-match")  # profile first: match subjects can use built profiles
RESEARCH_TURNS = 6  # venus.training.research runs with max_turns=6
EXTRA_CALLS = 2  # a reminder and a repair can add a call each


def parse_args(argv):
    a = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    a.add_argument("--cases", type=int, default=None, help="use at most this many cases (default: all)")
    a.add_argument("--lead-rule", choices=LEAD_RULES, default="explicit",
                   help="explicit: only rows marking '(lead)'; explicit_or_sole: also a row with one investor")
    a.add_argument("--top-k", type=int, default=10)
    a.add_argument("--max-turns", type=int, default=TRAIN_CASE_LIMITS["max_turns"], help="model turns per case")
    a.add_argument("--max-web-calls", type=int, default=TRAIN_CASE_LIMITS["max_web_calls"], help="web calls per case")
    a.add_argument("--max-model-calls", type=int, default=60, help="model calls for the whole run")
    a.add_argument("--max-cala-calls", type=int, default=5, help="Cala calls --refresh may make")
    a.add_argument("--refresh", action="store_true", help="call Cala for queries not in the cache")
    a.add_argument("--dry-run", action="store_true", help="print the estimate; call no model")
    a.add_argument("--no-model-cache", action="store_true")
    a.add_argument("--cala-cache", default=str(ROOT / "app" / "data" / "cache"))
    a.add_argument("--strategies", default=str(ROOT / "leadline" / "strategies"))
    a.add_argument("--runs", default=str(ROOT / "leadline" / "runs"))
    a.add_argument("--plugin", choices=PLUGINS + ("both",), default="leadline-match")
    a.add_argument("--promote", action="store_true", help="gate each draft; save passing ones as <plugin>-default")
    a.add_argument("--min-score", type=float, default=0.5, help="--promote: lowest mean case score to promote")
    a.add_argument("--drop-leaking", action="store_true",
                   help="--promote: leave out tendencies that name a training answer (listed in notes) instead of "
                        "refusing the draft")
    a.add_argument("--profile-db", default=None,
                   help="build match subjects' profiles with leadline-profile into this SQLite file (LeadlineDb)")
    args = a.parse_args(argv)
    for name in ("max_turns", "max_model_calls"):
        if getattr(args, name) < 1:
            a.error(f"--{name.replace('_', '-')} must be >= 1")
    for name in ("max_web_calls", "max_cala_calls"):
        if getattr(args, name) < 0:
            a.error(f"--{name.replace('_', '-')} must be >= 0")
    if args.cases is not None and args.cases < 1:
        a.error("--cases must be >= 1")
    return args


def _load_env_file():
    """VENUS_ENV_FILE, else the root .env, else venus/.env (where the keys live today); shell values win."""
    for path in (os.environ.get("VENUS_ENV_FILE"), ROOT / ".env", ROOT / "venus" / ".env"):
        if path and Path(path).is_file():
            load_env(Path(path))
            return Path(path)
    return None


def _model_check(env):
    """(base_model, None) or (base_model, why the training model can't be built)."""
    base_model = training_base_model(env)
    try:
        resolve_model(base_model, env)
    except Exception as e:
        return base_model, f"{type(e).__name__}: {e}"
    return base_model, None


def _plain(text) -> str:
    return " " + " ".join(re.sub(r"[^0-9a-z]+", " ", str(text).casefold()).split()) + " "


def guard_tools(tools, names):
    """Answer-leak guard for time-split training: a web call whose query or URL names a training subject is refused
    (the web knows who led that round; the case asks as of the day before). Other calls pass through unchanged."""
    blocked = [_plain(n) for n in names if len(_plain(n).strip()) >= 3]

    def wrap(tool):
        def fn(arguments):
            text = _plain(" ".join(str(arguments.get(k, "")) for k in ("query", "url")))
            hit = next((b.strip() for b in blocked if b in text), None)
            if hit:
                return {"error": f"blocked: the call names a training subject ({hit}); research the market, "
                                 "not this company"}
            return tool.fn(arguments)
        return Tool(tool.name, tool.description, tool.parameters, fn, web=tool.web)
    return [wrap(t) if t.web else t for t in tools]


def _queries():
    from ingest.build_dataset import QUERIES
    return list(QUERIES)


def _print(data: dict) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def main(argv=None, *, cala_transport=None, web_transport=None, model_factory=None, environ=None) -> int:
    args = parse_args(argv)
    if environ is None:
        _load_env_file()
        environ = os.environ
    env = dict(environ)
    env.setdefault("VENUS_CACHE_DIR", str(ROOT / ".venus_cache"))
    env["VENUS_MODEL_CACHE"] = "0" if args.no_model_cache else env.get("VENUS_MODEL_CACHE", "1")

    cala_http = httpx.Client(transport=cala_transport, timeout=180.0)
    try:
        rows, cala = load_rows(_queries(), args.cala_cache, refresh=args.refresh, max_cala_calls=args.max_cala_calls,
                               http_client=cala_http, api_key=env.get("CALA_API_KEY") or None)
    except CaseError as e:
        print(f"STOP (Cala): {e}")
        return 2
    except Exception as e:  # the Cala client's own errors (bad key, HTTP error)
        print(f"STOP (Cala): {type(e).__name__}: {e}")
        return 2
    finally:
        cala_http.close()

    wanted = PLUGINS if args.plugin == "both" else (args.plugin,)
    match_cases, report = build_cases(rows, lead_rule=args.lead_rule, top_k=args.top_k, limit=args.cases)
    profile_cases, profile_report = build_profile_cases(rows, limit=args.cases)
    if "leadline-match" in wanted and not match_cases:
        print(f"STOP: the Cala pull names no lead investor in any usable row ({report}). Try "
              "--lead-rule explicit_or_sole, or add broad queries to app/ingest/build_dataset.py QUERIES (ask the "
              "team first) and run with --refresh.")
        return 3
    if "leadline-profile" in wanted and not profile_cases:
        print(f"STOP: no company in the Cala pull has a known country, stage or sector ({profile_report}).")
        return 3
    cases_by = {"leadline-match": match_cases, "leadline-profile": profile_cases}
    reports = {"leadline-match": report, "leadline-profile": profile_report}

    web_count = {"n": 0}
    key = key_from_env(env)
    tools, tools_by = [], {name: [] for name in PLUGINS}
    if key or web_transport is not None:
        hooks = {"request": [lambda request: web_count.__setitem__("n", web_count["n"] + 1)]}
        # fresh_ttl=None and no fresh scrape: an identical rerun replays every web result from the cache.
        client = ContextDev(api_key=key or "stub", http_client=httpx.Client(transport=web_transport,
                                                                              event_hooks=hooks),
                            cache=cache_from_env(env), fresh_ttl=None)
        tools = web_tools(client, allow_fresh=False)
        # Only the match run hides an answer the web knows (who led the subject's round). A profile case's answer
        # is the company's own country/stage/sectors, and looking the company up is the profile task itself.
        subjects = list(dict.fromkeys(c["input"]["subject"]["name"] for c in match_cases))
        tools_by = {"leadline-profile": tools, "leadline-match": guard_tools(tools, subjects)}
    limits = {"max_turns": args.max_turns, "max_web_calls": args.max_web_calls}
    if len(wanted) == 1:
        name = wanted[0]
        base = {"plugin": name, "cases": len(cases_by[name]), "case_ids": [c["id"] for c in cases_by[name]],
                "build_report": reports[name], "limits": limits, **cala}
    else:
        base = {"plugin": "both", "cases": {n: len(cases_by[n]) for n in wanted},
                "build_report": {n: reports[n] for n in wanted}, "limits": limits, **cala}

    if args.dry_run:
        research = bool(tools)
        base_model, problem = _model_check(env)
        n_cases = sum(len(cases_by[n]) for n in wanted)
        profile_builds = len(match_cases) if args.profile_db and "leadline-match" in wanted else 0
        _print({**base, "dry_run": True, "web_tools": research, "base_model": base_model,
                "model_config_error": problem, "estimate": {
            "model_calls_max": min(args.max_model_calls,
                                   len(wanted) * (RESEARCH_TURNS + EXTRA_CALLS if research else 0)
                                   + (n_cases + profile_builds) * (args.max_turns + EXTRA_CALLS)),
            "web_calls_max": len(wanted) * MAX_WEB_CALLS + n_cases * args.max_web_calls if research else 0,
            "profile_builds_max": profile_builds,
            "cala_calls": cala["cala_calls"]}})
        return 4 if problem else 0

    base_model, problem = _model_check(env)
    if problem:
        print(f"STOP (model config): {problem}. Check VENUS_TRAIN_PROVIDER / VENUS_TRAIN_MODEL in your .env.")
        return 4

    plugins = load_plugins(ROOT / "leadline" / "plugins")
    factory = model_factory or default_model_factory(max_model_calls=args.max_model_calls, environ=env)
    model = factory(base_model)  # one model, one budget (--max-model-calls) for the whole run
    runs, promoted, extra = {}, {}, {}
    for name in wanted:
        cases = cases_by[name]
        if name == "leadline-match" and args.profile_db:
            tendencies = None
            if promoted.get("leadline-profile", {}).get("promoted"):
                tendencies = StrategyStore(Path(args.strategies)).get("leadline-profile-default").tendencies
            runner = case_runner(model, plugin=plugins["leadline-profile"], tendencies=tendencies,
                                 max_turns=args.max_turns, max_web_calls=0)
            try:
                cases, reports[name] = build_cases(rows, lead_rule=args.lead_rule, top_k=args.top_k,
                                                   limit=args.cases, profile_store=LeadlineDb(args.profile_db),
                                                   profile_run=runner, profile_key_tag=strategy_tag(tendencies))
            except Exception as e:  # a model failure or a profile the store refused
                _print({**base, "status": "error", "error": f"profile build: {type(e).__name__}: {e}",
                        "profiles_built": runner.calls, "web_http_calls": web_count["n"]})
                return 1
            extra["profiles_built"] = runner.calls
            if not cases:
                _print({**base, **extra, "status": "error",
                        "error": f"no match case left after building profiles ({reports[name]})"})
                return 3
        runs[name] = _train_one(plugins[name], cases, model, tools_by[name], base_model, limits, args, web_count)
        if args.promote and runs[name]["status"] != "error":
            promoted[name] = promote(plugins[name], runs[name], cases, Path(args.strategies), args.min_score,
                                     base_model, drop_leaking=args.drop_leaking)
        elif args.promote:
            promoted[name] = {"promoted": False, "reasons": ["training failed"]}

    if len(wanted) == 1:
        out = {**base, **runs[wanted[0]], **extra}
    else:
        statuses = {r["status"] for r in runs.values()}
        status = "ok" if statuses == {"ok"} else "error" if "error" in statuses else "partial"
        out = {**base, **extra, "status": status, "runs": runs, "web_http_calls": web_count["n"]}
    if args.promote:
        out["promoted"] = promoted
    _print(out)
    if any(r["status"] not in ("ok", "partial") for r in runs.values()):
        return 1
    if args.promote and not all(p.get("promoted") for p in promoted.values()):
        return 5
    return 0


def _train_one(plugin, cases, model, tools, base_model, limits, args, web_count) -> dict:
    """Venus training for one plugin -> its ledger (also written to runs/<trace_id>/ledger.json)."""
    raw = {"venus_version": VENUS_VERSION, "plugin": plugin.name, "mode": "training",
           "cases": [{"id": c["id"], "input": c["input"], "expected": c["expected"]} for c in cases]}
    head = {"plugin": plugin.name, "cases": len(cases), "case_ids": [c["id"] for c in cases]}
    try:
        request = check_request(raw, {plugin.name: plugin}, StrategyStore(Path(args.strategies)))
        resp = train(request, model, web_tools=tools, strategies_dir=Path(args.strategies), runs_dir=Path(args.runs),
                     base_model=base_model, case_limits=limits)
    except VenusError as e:
        return {**head, "status": "error", "error": e.to_dict(), "web_http_calls": web_count["n"]}
    usage = resp.get("usage", {})
    scores = resp.get("scores", [])
    ledger = {**head, "status": resp["status"], "trace_id": resp.get("trace_id"),
              "draft_strategy": resp.get("draft_strategy"), "base_model": base_model,
              "model_calls": usage.get("model_calls", 0), "model_cache_hits": usage.get("cache_hits", 0),
              "input_tokens": usage.get("input_tokens", 0), "output_tokens": usage.get("output_tokens", 0),
              "web_calls": usage.get("web_calls", 0), "web_http_calls": web_count["n"],
              "seconds": usage.get("seconds"), "scores": scores,
              "mean_score": round(sum(s["total"] for s in scores) / len(scores), 4) if scores else None,
              "warnings": resp.get("warnings", []), "error": resp.get("error")}
    if resp.get("trace_id"):
        folder = Path(args.runs) / resp["trace_id"]
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "ledger.json").write_text(json.dumps(ledger, indent=2, ensure_ascii=False, default=str))
    return ledger


def strategy_tag(tendencies) -> str:
    """Short hash of the profile tendencies a stored profile was built with ("base" = none), so a profile built under
    another strategy is never reused for match cases."""
    if not tendencies:
        return "base"
    texts = [getattr(t, "text", t) for t in tendencies]
    return hashlib.sha1(json.dumps(texts, sort_keys=True).encode()).hexdigest()[:12]


def answer_names(cases) -> list:
    """Names a promoted tendency must not contain: each case's subject (or user) and the leads it hides."""
    names = []
    for c in cases:
        value, expected = c["input"], c.get("expected") or {}
        if "subject" in value:
            names.append(value["subject"]["name"])
            by_id = {x["id"]: x.get("name") for x in value.get("candidates", [])}
            names += [by_id.get(m["candidate_id"]) for m in expected.get("matches", [])]
        if "user" in value:
            names.append(value["user"]["name"])
    return [n for n in dict.fromkeys(names) if n and len(n.strip()) >= 3]


GENERIC_WORDS = {  # name words too common to signal a leak on their own
    "ventures", "venture", "capital", "partners", "partner", "green", "energy", "fusion", "pharma", "computing",
    "money", "health", "group", "systems", "global", "invest", "investments", "holdings", "europe", "european",
    "digital", "technologies", "technology", "funds", "growth", "innovation", "council", "founders", "factory",
    "defence", "defense", "angels", "series", "storage", "network", "networks", "robotics", "therapeutics",
}


def leaking_names(text: str, names) -> list:
    """The names that `text` mentions: the whole name, or one of its distinctive words (5+ letters, not generic),
    e.g. "Mistral" for "Mistral AI"; "green" alone never counts for "Green Voltis"."""
    plain = _plain(text)
    hits = []
    for name in names:
        words = [w for w in _plain(name).split() if len(w) >= 5 and w not in GENERIC_WORDS]
        if _plain(name) in plain or any(f" {w} " in plain for w in words):
            hits.append(name)
    return hits


def promote(plugin, run, cases, strategies_dir, min_score, base_model, now=None, drop_leaking=False) -> dict:
    """Gate the run's draft (or the seed tendencies) and save it as <plugin>-default with status "validated".
    A tendency that names a training answer blocks promotion, or with `drop_leaking` is left out (and listed in
    notes). -> {promoted, strategy, from, reasons, gate, dropped}."""
    reasons = []
    if run.get("status") not in ("ok", "partial"):
        reasons.append(f"training status is {run.get('status')}")
    mean = run.get("mean_score")
    if mean is None or mean < min_score:
        reasons.append(f"mean score {mean} is under --min-score {min_score}")
    draft_id = run.get("draft_strategy")
    if draft_id:
        data = json.loads((Path(strategies_dir) / f"{draft_id}.json").read_text())
    else:
        data = {"base_model": dict(base_model), "tendencies": [t.to_dict() for t in plugin.seed_tendencies]}
    names = answer_names(cases)
    kept, dropped = [], []
    for t in data["tendencies"]:
        hits = leaking_names(" ".join([t.get("text", "")] + list(t.get("sources") or [])), names)
        if not hits:
            kept.append(t)
        elif drop_leaking:
            dropped.append({"id": t.get("id"), "names": hits, "text": t.get("text", "")})
        else:
            reasons.append(f"answer leak: tendency {t.get('id')} names {', '.join(hits)}")
    now = now or datetime.now(timezone.utc)
    candidate = {"id": f"{plugin.name}-default", "plugin": plugin.name, "plugin_version": plugin.version,
                 "status": "validated", "base_model": data["base_model"], "tendencies": kept,
                 "created_at": now.isoformat(timespec="seconds")}
    if data.get("settings"):
        candidate["settings"] = data["settings"]
    result = gate(plugin, Strategy.from_dict(candidate), cases)
    reasons += [f"gate: {r}" for r in result["reasons"]]
    out = {"promoted": False, "strategy": candidate["id"], "from": draft_id or "seed tendencies",
           "reasons": reasons, "gate": result, "dropped": dropped}
    if reasons:
        return out
    candidate["notes"] = json.dumps({"trace_id": run.get("trace_id"), "from": out["from"], "mean_score": mean,
                                     "dropped_for_leak": dropped,
                                     "score_note": "scores were measured with every draft tendency, including any "
                                                   "dropped_for_leak" if dropped else None,
                                     "scores": run.get("scores"), "cases": [c["id"] for c in cases],
                                     "gate": {"passed": True, "metrics": result["metrics"]},
                                     "promoted_at": candidate["created_at"]}, ensure_ascii=False, default=str)
    from jsonschema import Draft202012Validator
    errors = list(Draft202012Validator(load_schema("strategy")).iter_errors(candidate))
    if errors:
        return {**out, "reasons": [f"strategy invalid: {errors[0].message}"]}
    folder = Path(strategies_dir)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{candidate['id']}.json").write_text(json.dumps(candidate, indent=2, ensure_ascii=False) + "\n")
    out["promoted"] = True
    return out


if __name__ == "__main__":
    sys.exit(main())
