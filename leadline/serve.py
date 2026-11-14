"""Run the Leadline service and its background worker on 127.0.0.1.

    python leadline/serve.py --db leadline/data/leadline.db --port 8765 [--no-worker] [--fake-model]
                             [--env-file venus/.env]

The service trusts its caller (the frontend's server code), so it only ever binds to 127.0.0.1. API keys come from
the process environment (and `--env-file`, which never overrides a set variable); no key is ever printed.
`--fake-model` answers every profile and match run offline with a valid made-up answer and turns web tools and Cala
off: for smoke runs that must not spend anything.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from db import LeadlineDb  # noqa: E402
from jobs import Worker, handlers, make_agents  # noqa: E402
from runtime import DEFAULT_AGENT_DIR  # noqa: E402
from service import create_app  # noqa: E402

HOST = "127.0.0.1"
OFFLINE_DROP = ("CONTEXT_DEV_API_KEY", "LEADLINE_LIVE_CALA", "CALA_API_KEY")  # --fake-model: nothing leaves the host


def load_env_file(path, environ) -> list:
    """KEY=VALUE lines (# comments, optional quotes) into `environ`, never over a set variable. Returns the names
    set (never the values)."""
    names = []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.removeprefix("export ").split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in environ:
            environ[key] = value
            names.append(key)
    return names


# --- offline model ------------------------------------------------------------------------------------------------

def _input_of(messages) -> dict:
    for m in messages:
        content = m.get("content") if isinstance(m, dict) else None
        if isinstance(content, str) and content.startswith("Input:\n"):
            return json.loads(content[len("Input:\n"):])
    raise ValueError("no plugin input in the messages")


def _fake_profile(data: dict) -> dict:
    user, fields = data["user"], data["user"].get("fields") or {}
    fact = {"id": "form-1", "kind": "dataset", "ref": "signup form", "quote": json.dumps(fields)[:200]}
    profile = {"id": user["id"], "kind": user["kind"], "name": user["name"], "website": user.get("website"),
               "description": fields.get("oneLiner"), "facts": [fact], "sources": {}}
    if user["kind"] == "startup":
        profile.update(stage=fields.get("stage"), sectors=[fields["sector"]] if fields.get("sector") else [],
                       country=(fields.get("location") or "").split(",")[-1].strip() or None)
        if fields.get("raiseEurM"):
            profile["raising"] = {"amount": float(fields["raiseEurM"]) * 1_000_000, "currency": "EUR"}
    else:
        rows = data.get("cala_facts") or []
        profile.update(stages=sorted({r["stage"].lower() for r in rows if r.get("stage")}),
                       sectors=sorted({r["sector"] for r in rows if r.get("sector")}), regions=[])
    for field in ("description", "country", "stage", "stages", "sectors", "raising"):
        if profile.get(field):
            profile["sources"][field] = {"facts": ["form-1"]}
    return {"profile": profile, "rating": {"total": 0.5, "parts": {"fit": 0.5}, "sources": ["form-1"]},
            "changes": []}


def _fake_match(data: dict) -> dict:
    kind = "investor" if data["request"]["direction"] == "startup_to_investors" else "company"
    top = data["candidates"][:data["request"]["top_k"]]
    evidence = [{"id": f"e{i}", "kind": "dataset", "ref": c["id"]} for i, c in enumerate(top, 1)]
    matches = [{"candidate_id": c["id"], "candidate_type": kind, "rank": i, "score": round(max(0.1, 0.9 - 0.05 * i), 2),
                "score_parts": {"fit": 0.5}, "role": "unknown", "active": {"status": "unknown"},
                "confidence": "low", "reasons": [{"text": "offline fake model: order of the fit score",
                                                  "evidence": [f"e{i}"]}]}
               for i, c in enumerate(top, 1)]
    return {"matches": matches, "rejected": [], "evidence": evidence, "warnings": ["offline fake model"]}


def fake_answer(data: dict) -> dict:
    """A valid output for the plugin whose input `data` is (profile: has `user`; match: has `subject`)."""
    if "user" in data:
        return _fake_profile(data)
    if "subject" in data:
        return _fake_match(data)
    raise ValueError("unknown plugin input")


def offline_model(agent_root=None):
    """A FakeModel (from the injected agent) that answers from the run's own input."""
    root = Path(agent_root or os.environ.get("LEADLINE_AGENT_DIR") or DEFAULT_AGENT_DIR).resolve()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from leadline_agent.fake import FakeModel, fake_text

    def reply(messages, tools=None, tool_choice=None):
        return fake_text(json.dumps({"output": fake_answer(_input_of(messages)), "sources": []}))
    return FakeModel(reply)


# --- launcher -----------------------------------------------------------------------------------------------------

def build(db_path, *, worker=True, fake_model=False, environ=None, agent_root=None):
    """(app, worker or None) for these options; used by main() and the tests."""
    environ = dict(os.environ if environ is None else environ)
    db = LeadlineDb(db_path)
    if not worker:
        return create_app(db), None
    model = None
    if fake_model:
        for name in OFFLINE_DROP:
            environ.pop(name, None)
        model = offline_model(agent_root)
    profile_agent, match_agent = make_agents(environ, agent_root=agent_root, model=model)
    if fake_model:
        profile_agent.web_tools = []  # no Context.dev even if a key is set some other way
    w = Worker(db, handlers(profile_agent, match_agent))
    return create_app(db, w), w


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", default=str(HERE / "data" / "leadline.db"))
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-worker", action="store_true", help="serve reads only; queued jobs wait")
    parser.add_argument("--fake-model", action="store_true", help="offline answers; no model, web or Cala calls")
    parser.add_argument("--env-file", help="KEY=VALUE file with API keys (never overrides the environment)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if args.env_file:
        names = load_env_file(args.env_file, os.environ)
        logging.info("loaded %d variables from %s", len(names), args.env_file)
    app, _ = build(args.db, worker=not args.no_worker, fake_model=args.fake_model)

    import uvicorn
    uvicorn.run(app, host=HOST, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
