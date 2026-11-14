"""The trained Leadline agents, for real (phase 9): load both promoted `*-default` strategies, check they are
validated, and run one `Venus.handle(mode="run")` per plugin with the runtime tools (Context.dev web + Cala, whose
replies are stored in a LeadlineDb) and the model reply cache on, so a rerun reuses cached replies.

Spends Anthropic and Context.dev credits on the first run, and at most VENUS_CALA_MAX_CALLS (2 here) Cala calls per
run; cache hits are free.

    cd tests/live && VENUS_LIVE=1 VENUS_ENV_FILE=../../venus/.env ../../venus/.venv/bin/python -m pytest -q -rs -s \
        test_trained_agent.py
"""
import json
import sys

import pytest
from conftest import ROOT, need

sys.path.insert(0, str(ROOT / "leadline"))

from db import LeadlineDb  # noqa: E402
from venus.cala import Cala, cala_tools  # noqa: E402
from venus.serve import Venus  # noqa: E402
from venus.strategy import StrategyStore  # noqa: E402

STRATEGIES = ROOT / "leadline" / "strategies"
PLUGINS = ROOT / "leadline" / "plugins"
MATCH_REQUEST = ROOT / "app" / "contracts" / "venus_request.example.json"


@pytest.fixture
def live_env(monkeypatch):
    need("ANTHROPIC_API_KEY", "CONTEXT_DEV_API_KEY|CONTEXTDEV_API_KEY")
    monkeypatch.setenv("VENUS_MODEL_CACHE", "1")
    monkeypatch.setenv("VENUS_CACHE_DIR", str(ROOT / ".venus_cache"))
    monkeypatch.setenv("VENUS_CALA_MAX_CALLS", "2")
    monkeypatch.setenv("VENUS_CALA_CACHE_DIR", str(ROOT / "app" / "data" / "cache"))


def test_both_default_strategies_are_validated():
    need()  # the strategies exist only after the live training run
    store = StrategyStore(STRATEGIES)
    for plugin in ("leadline-profile", "leadline-match"):
        strategy = store.get(f"{plugin}-default")
        assert strategy.is_validated, f"{plugin}-default is {strategy.status}"
        notes = json.loads(strategy.notes)
        assert notes["trace_id"] and notes["gate"]["passed"] is True


def _venus(db, trace):
    return Venus(plugins_dir=PLUGINS, strategies_dir=STRATEGIES, runs_dir=None, env=False,
                 cala_factory=lambda: cala_tools(Cala(on_result=db.cala_hook(trace_id=trace))))


def _report(resp):
    print(f"\n{resp.get('plugin')}: status={resp['status']} usage={resp.get('usage')} warnings={resp.get('warnings')}")


def test_profile_agent_runs_and_its_profile_is_stored(live_env, tmp_path):
    db = LeadlineDb(tmp_path / "leadline.db")
    user = {"id": "u_live_northvolt", "kind": "startup", "name": "Northvolt", "website": "https://northvolt.com"}
    resp = _venus(db, "live-profile").handle({"venus_version": "1", "plugin": "leadline-profile", "mode": "run",
                                              "strategy": "leadline-profile-default", "input": {"user": user}})
    _report(resp)
    assert resp["status"] == "ok", resp.get("error")
    out = resp["outputs"][0]["output"]
    assert out["profile"]["name"] and out["changes"] == []
    version = db.put(user["id"], out["profile"], out["rating"], out["changes"], expected_version=0)
    assert db.get(user["id"])["version"] == version == 1


def test_match_agent_runs_on_the_example_request(live_env, tmp_path):
    db = LeadlineDb(tmp_path / "leadline.db")
    request = json.loads(MATCH_REQUEST.read_text())
    resp = _venus(db, "live-match").handle(request)
    _report(resp)
    assert resp["status"] == "ok", resp.get("error")
    out = resp["outputs"][0]["output"]
    ids = {c["id"] for c in request["input"]["candidates"]}
    assert all(m["candidate_id"] in ids for m in out["matches"])
    db.put_snapshot("shortlist", "live-example", out, mode="live", trace_id=resp["trace_id"])
    assert db.latest_snapshot("shortlist", "live-example")["payload"] == out
