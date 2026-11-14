"""F1 injection loader and Leadline-to-Agent runtime bridge contract."""
import sys
from pathlib import Path

import pytest

from runtime import AgentBridge, AgentLoadError, load_agent
from db import LeadlineDb


@pytest.fixture
def db(tmp_path):
    return LeadlineDb(tmp_path / "leadline.db")


class StubAgent:
    def __init__(self, result=None, settings=None):
        self.result = result or {"status": "ok", "outputs": [], "trace_id": "trace"}
        self.strategy_settings = settings or {}
        self.calls = []

    def settings(self, plugin_id, strategy=None):
        self.calls.append(("settings", plugin_id, strategy))
        return self.strategy_settings

    def run(self, plugin_id, input_data, strategy=None, *, trace_id=None, on_cala_result=None):
        self.calls.append(("run", plugin_id, input_data, strategy, trace_id, on_cala_result))
        return {**self.result, "trace_id": trace_id}


def test_load_agent_imports_only_from_injected_agent_root(tmp_path, monkeypatch):
    agent_root = tmp_path / "agent"
    package = agent_root / "leadline_agent"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(
        "class Agent:\n"
        "    def __init__(self, root_dir=None, **kwargs):\n"
        "        self.root_dir = root_dir\n"
        "        self.kwargs = kwargs\n"
    )
    monkeypatch.setattr("runtime.DEFAULT_AGENT_DIR", agent_root)

    agent = load_agent(web_tools=[])

    assert Path(agent.root_dir) == agent_root
    assert agent.kwargs["web_tools"] == []
    assert str(agent_root) in sys.path


def test_load_agent_reports_missing_injected_root(tmp_path):
    with pytest.raises(AgentLoadError, match="agent root does not exist"):
        load_agent(tmp_path / "missing-agent")


def test_bridge_passes_cala_hook_and_prefilter_settings_to_agent(db):
    agent = StubAgent(settings={"rules": [], "max_candidates": 1})
    bridge = AgentBridge(db, agent=agent)
    subject = {"id": "startup", "kind": "startup", "name": "Startup"}
    candidates = [
        {"id": "investor-1", "kind": "investor", "name": "Investor 1"},
        {"id": "investor-2", "kind": "investor", "name": "Investor 2"},
    ]
    payload = {"subject": subject, "candidates": candidates,
               "request": {"direction": "startup_to_investors", "top_k": 2}}

    result = bridge.run("leadline-match", payload)

    settings_call, run_call = agent.calls
    assert settings_call == ("settings", "leadline-match", None)
    _, plugin_id, model_input, strategy, trace_id, hook = run_call
    assert plugin_id == "leadline-match" and strategy is None
    assert len(model_input["candidates"]) == 1
    assert model_input["candidates"][0]["id"] == "investor-1"
    assert trace_id and result["trace_id"] == trace_id
    assert callable(hook)

    hook("entity_get", {"id": "cala-id"}, {"id": "cala-id", "name": "Investor 1"})
    assert db.entity("cala-id")["name"] == "Investor 1"
    assert db.entity("cala-id")["provenance"]["traceId"] == trace_id


def test_bridge_does_not_prefilter_profile_payload(db):
    agent = StubAgent()
    bridge = AgentBridge(db, agent=agent)
    payload = {"profile": {"id": "founder", "kind": "startup"}, "cala_facts": []}

    bridge.run("leadline-profile", payload)

    assert len(agent.calls) == 1
    assert agent.calls[0][1:4] == ("leadline-profile", payload, None)


def test_bridge_converts_settings_error_to_agent_error_response(db):
    class AgentError(Exception):
        code = "strategy_not_validated"
        message = "strategy is draft"
        path = "status"

    class BrokenSettingsAgent(StubAgent):
        def settings(self, plugin_id, strategy=None):
            raise AgentError("strategy is draft")

    result = AgentBridge(db, agent=BrokenSettingsAgent()).run(
        "leadline-match", {"subject": {}, "candidates": [], "request": {"direction": "startup_to_investors"}})

    assert result == {"plugin": "leadline-match", "mode": "run", "strategy": "leadline-match-default",
                      "status": "error", "outputs": [], "trace_id": result["trace_id"],
                      "usage": {}, "warnings": [],
                      "error": {"code": "strategy_not_validated", "message": "strategy is draft",
                                "path": "status"}}


def test_bridge_returns_empty_match_without_calling_agent_when_prefilter_drops_everyone(db):
    agent = StubAgent(settings={"rules": []})
    payload = {"subject": {"id": "s", "kind": "startup", "name": "Startup"},
               "candidates": [{"id": "wrong", "kind": "startup", "name": "Wrong kind"}],
               "request": {"direction": "startup_to_investors", "top_k": 5}}

    result = AgentBridge(db, agent=agent).run("leadline-match", payload)

    assert len(agent.calls) == 1  # settings only; no model call
    assert result["status"] == "ok" and result["trace_id"]
    assert result["usage"] == {"model_calls": 0, "input_tokens": 0, "output_tokens": 0,
                                "web_calls": 0, "cache_hits": 0, "seconds": 0}
    assert result["outputs"][0]["output"]["matches"] == []
    assert result["outputs"][0]["output"]["rejected"] == []


MATCH_PAYLOAD = {"subject": {}, "candidates": [], "request": {"direction": "startup_to_investors"}}


def test_bridge_reraises_unrelated_exception_that_has_a_code(db):
    class Unrelated(RuntimeError):
        code = "looks_like_an_agent_code"

    class BuggyAgent(StubAgent):
        def settings(self, plugin_id, strategy=None):
            raise Unrelated("a real bug, not an agent error")

    with pytest.raises(Unrelated):
        AgentBridge(db, agent=BuggyAgent()).run("leadline-match", MATCH_PAYLOAD)


def _assert_converted(db, agent_error_class):
    class MissingStrategyAgent(StubAgent):
        def settings(self, plugin_id, strategy=None):
            raise agent_error_class("strategy_not_found", "no leadline-match-default", None)

    result = AgentBridge(db, agent=MissingStrategyAgent()).run("leadline-match", MATCH_PAYLOAD)

    assert result["status"] == "error"
    assert result["error"] == {"code": "strategy_not_found", "message": "no leadline-match-default"}


def test_bridge_converts_real_venus_agent_error(db):
    _assert_converted(db, pytest.importorskip("venus.agent").AgentError)


def test_bridge_converts_exported_leadline_agent_error(db, monkeypatch):
    export = Path(__file__).resolve().parents[2] / "dist" / "leadline-agent"
    if not (export / "leadline_agent" / "__init__.py").is_file():
        pytest.skip("no exported agent at dist/leadline-agent (run venus export)")
    for name in [m for m in sys.modules if m == "leadline_agent" or m.startswith("leadline_agent.")]:
        monkeypatch.delitem(sys.modules, name)  # an earlier test may have cached a fake leadline_agent
    monkeypatch.syspath_prepend(str(export))
    _assert_converted(db, pytest.importorskip("leadline_agent").AgentError)


INJECTED = Path(__file__).resolve().parents[1] / "agent"


@pytest.mark.skipif(not (INJECTED / "leadline_agent" / "__init__.py").is_file(),
                    reason="no injected agent at leadline/agent (run scripts/inject_agent.sh)")
def test_injected_agent_runs_leadline_profile_offline(db, monkeypatch):
    import json
    import shapes
    for name in [m for m in sys.modules if m == "leadline_agent" or m.startswith("leadline_agent.")]:
        monkeypatch.delitem(sys.modules, name)  # an earlier test may have cached a fake leadline_agent
    monkeypatch.syspath_prepend(str(INJECTED))
    from leadline_agent.fake import FakeModel, fake_text

    record = db.upsert_founder({"profile": {"startupName": "Carbonlens", "oneLiner": "Scope 3 emissions",
                                            "sector": "climate", "stage": "seed", "location": "Berlin",
                                            "region": "europe", "raiseEurM": 1.5, "competitors": [],
                                            "customers": "manufacturers"},
                                "founderName": "Alex", "email": "a@b.c", "discoverable": True})
    payload = shapes.founder_profile_input(record, [], as_of="2026-11-14")
    answer = {"profile": {"id": payload["user"]["id"], "kind": "startup", "name": "Carbonlens", "stage": "seed",
                          "facts": [{"id": "u-1", "kind": "web", "url": "https://carbonlens.example"}],
                          "sources": {"stage": {"facts": ["u-1"]}}},
              "rating": {"total": 0.5, "parts": {"fit": 0.5}, "sources": ["u-1"]}, "changes": []}
    model = FakeModel([fake_text(json.dumps({"output": answer, "sources": ["https://carbonlens.example"]}))])

    agent = load_agent(INJECTED, model=model, web_tools=[], cala=False, environ={})
    assert type(agent).__module__.startswith("leadline_agent")  # the injected package, not venus
    result = AgentBridge(db, agent=agent).run("leadline-profile", payload)

    assert result["status"] == "ok", result
    assert result["outputs"][0]["output"]["profile"]["name"] == "Carbonlens"
