"""Runtime Cala tools (venus.cala): request shapes, the cache shared with app/ingest/cala_client.py, the per-run call
budget, and run-only gating (Cala holds the training answers, so training never gets these tools).
Every test uses httpx.MockTransport and no key from the shell: no real Cala call is possible."""
import importlib.util
import json
from pathlib import Path

import httpx
import pytest

from venus.cala import Cala, cala_tools
from venus.errors import CalaError
from venus.fake import FakeModel, fake_text, fake_tool_call
from venus.plugin import load_plugin
from venus.tools import Tool, collect_tools

APP_CLIENT = Path(__file__).resolve().parents[2] / "app" / "ingest" / "cala_client.py"
UUID = "5a55e4a2-7bae-49ae-8893-fb400096c36b"
QUERY_REPLY = {"results": [{"company": f"C{i}", "amount": "1"} for i in range(80)],
               "entities": [{"id": UUID, "name": "Mistral AI", "entity_type": "Company", "mentions": ["x"]}]}
SEARCH_REPLY = {"content": "long text " * 50,
                "explainability": [{"content": "Mistral raised a seed round.", "references": ["r1"]}],
                "context": [{"id": "r1", "content": "Mistral AI raised EUR 105M led by Lightspeed. " * 40,
                             "origins": [{"source": {"name": "TechCrunch", "url": "https://techcrunch.com"},
                                          "document": {"name": "Mistral raises", "url": "https://tc.com/m"}}]}]}


@pytest.fixture(autouse=True)
def no_shell_key(monkeypatch):
    for name in ("CALA_API_KEY", "VENUS_CALA_MAX_CALLS", "VENUS_CALA_CACHE_DIR", "CALA_BASE_URL"):
        monkeypatch.delenv(name, raising=False)


class Recorder:
    """A MockTransport handler that records requests and serves replies by path; anything else fails the test."""
    def __init__(self, replies=None, status=200):
        self.replies = replies or {}
        self.status = status
        self.requests = []

    def __call__(self, request: httpx.Request):
        self.requests.append(request)
        for path, reply in self.replies.items():
            if request.url.path == path:
                return httpx.Response(self.status, json=reply)
        raise AssertionError(f"unexpected Cala request {request.method} {request.url}")

    def client(self):
        return httpx.Client(transport=httpx.MockTransport(self))


def make(tmp_path, recorder=None, key="test-key", **kw):
    recorder = recorder or Recorder()
    return Cala(api_key=key, http_client=recorder.client(), cache_dir=tmp_path / "cala", environ={}, **kw), recorder


# --- client ------------------------------------------------------------------------------------------------------

def test_request_shapes_and_key_header(tmp_path):
    rec = Recorder({"/v1/knowledge/query": QUERY_REPLY, "/v1/knowledge/search": SEARCH_REPLY,
                    "/v1/entities": {"entities": []}, f"/v1/entities/{UUID}": {"id": UUID}})
    cala, _ = make(tmp_path, rec, max_calls=10)
    cala.knowledge_query("seed rounds in Finland")
    cala.knowledge_search("seed rounds in Finland")
    cala.entity_search("Mistral", limit=5, entity_types=["Company"])
    cala.entity_get(UUID)
    q, s, e, g = rec.requests
    assert (q.method, q.url.path, json.loads(q.content)) == (
        "POST", "/v1/knowledge/query", {"input": "seed rounds in Finland", "return_entities": True})
    assert (s.method, s.url.path, json.loads(s.content)) == ("POST", "/v1/knowledge/search",
                                                              {"input": "seed rounds in Finland"})
    assert e.method == "GET" and dict(e.url.params) == {"name": "Mistral", "limit": "5", "entity_types": "Company"}
    assert g.method == "POST" and g.url.path == f"/v1/entities/{UUID}"
    assert all(r.headers["X-API-KEY"] == "test-key" for r in rec.requests)
    assert all("Authorization" not in r.headers for r in rec.requests)


def test_second_call_is_a_cache_hit_and_costs_nothing(tmp_path):
    rec = Recorder({"/v1/knowledge/query": QUERY_REPLY})
    cala, _ = make(tmp_path, rec, max_calls=1)
    assert cala.knowledge_query("q") == QUERY_REPLY
    assert cala.knowledge_query("q") == QUERY_REPLY
    assert len(rec.requests) == 1 and cala.calls == 1


def test_cache_is_shared_with_the_app_client(tmp_path):
    if not APP_CLIENT.is_file():
        pytest.skip("app/ingest/cala_client.py not in this checkout")
    spec = importlib.util.spec_from_file_location("app_cala_client", APP_CLIENT)
    app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app)
    rec = Recorder({"/v1/knowledge/query": QUERY_REPLY, "/v1/entities": {"entities": [{"id": UUID}]}})
    old = app.CalaClient(api_key="k", http_client=rec.client(), cache_dir=tmp_path / "cala",
                         base_url="https://api.cala.ai")
    old.knowledge_query("shared question")  # written by the app client
    cala, _ = make(tmp_path, Recorder(), key=None)  # no key, no network: must be a cache hit
    assert cala.knowledge_query("shared question") == QUERY_REPLY
    cala2, _ = make(tmp_path, rec)
    cala2.entity_search("Mistral", limit=20)  # written by venus.cala
    before = len(rec.requests)
    assert old.entity_search("Mistral", limit=20) == {"entities": [{"id": UUID}]}
    assert len(rec.requests) == before


def test_miss_without_key_is_a_config_error(tmp_path):
    cala, rec = make(tmp_path, key=None)
    with pytest.raises(CalaError) as e:
        cala.knowledge_query("never cached")
    assert e.value.code == "cala_config_missing" and rec.requests == []


def test_budget_counts_network_calls_only(tmp_path):
    rec = Recorder({"/v1/knowledge/query": QUERY_REPLY})
    cala, _ = make(tmp_path, rec, max_calls=2)
    cala.knowledge_query("a")
    cala.knowledge_query("a")  # hit
    cala.knowledge_query("b")
    with pytest.raises(CalaError) as e:
        cala.knowledge_query("c")
    assert e.value.code == "cala_budget" and len(rec.requests) == 2
    assert cala.knowledge_query("b") == QUERY_REPLY  # hits still work over the cap


def test_budget_comes_from_the_environment(tmp_path):
    cala = Cala(api_key="k", cache_dir=tmp_path, environ={"VENUS_CALA_MAX_CALLS": "7"})
    assert cala.max_calls == 7
    assert Cala(api_key="k", cache_dir=tmp_path, environ={}).max_calls == 3
    with pytest.raises(CalaError):
        Cala(api_key="k", cache_dir=tmp_path, environ={"VENUS_CALA_MAX_CALLS": "lots"})


def test_errors_are_not_cached(tmp_path):
    bad = Recorder({"/v1/knowledge/query": {"detail": "nope"}}, status=401)
    cala, _ = make(tmp_path, bad, max_calls=5)
    with pytest.raises(CalaError) as e:
        cala.knowledge_query("q")
    assert e.value.code == "cala_failed" and "CALA_API_KEY" in e.value.message
    assert not list((tmp_path / "cala").glob("*.json"))


def test_network_error_is_a_cala_error(tmp_path):
    def boom(request):
        raise httpx.ConnectError("down")
    cala = Cala(api_key="k", http_client=httpx.Client(transport=httpx.MockTransport(boom)),
                cache_dir=tmp_path, environ={})
    with pytest.raises(CalaError) as e:
        cala.knowledge_query("q")
    assert e.value.code == "cala_failed"


@pytest.mark.parametrize("bad", ["../secrets", "abc", UUID + "/x", ""])
def test_entity_get_refuses_ids_that_are_not_uuids(tmp_path, bad):
    cala, rec = make(tmp_path)
    with pytest.raises(CalaError) as e:
        cala.entity_get(bad)
    assert e.value.code == "cala_bad_argument" and rec.requests == []


def test_entity_search_checks_its_arguments(tmp_path):
    cala, rec = make(tmp_path)
    for name, limit in (("", 5), ("x" * 101, 5), ("ok", 0), ("ok", 101)):
        with pytest.raises(CalaError):
            cala.entity_search(name, limit=limit)
    assert rec.requests == []


def test_on_result_sees_hits_and_misses(tmp_path):
    seen = []
    rec = Recorder({"/v1/knowledge/query": QUERY_REPLY})
    cala, _ = make(tmp_path, rec, on_result=lambda kind, request, reply: seen.append((kind, request, reply)))
    cala.knowledge_query("q")
    cala.knowledge_query("q")
    assert [s[0] for s in seen] == ["knowledge_query", "knowledge_query"]
    assert seen[0][1] == {"input": "q"} and seen[0][2] == QUERY_REPLY


# --- tools -------------------------------------------------------------------------------------------------------

def tools_by_name(cala):
    return {t.name: t for t in cala_tools(cala)}


def test_tools_are_run_only_and_named(tmp_path):
    cala, _ = make(tmp_path)
    tools = tools_by_name(cala)
    assert set(tools) == {"cala_knowledge_query", "cala_knowledge_search", "cala_entity_search", "cala_entity_get"}
    assert all(t.run_only and not t.web for t in tools.values())


def test_query_tool_trims_rows_and_entities(tmp_path):
    cala, _ = make(tmp_path, Recorder({"/v1/knowledge/query": QUERY_REPLY}))
    out = tools_by_name(cala)["cala_knowledge_query"].fn({"question": "q"})
    assert len(out["results"]) == 50 and out["rows_total"] == 80 and out["truncated"] is True
    assert out["entities"] == [{"id": UUID, "name": "Mistral AI", "entity_type": "Company"}]


def test_search_tool_keeps_claims_and_sources(tmp_path):
    cala, _ = make(tmp_path, Recorder({"/v1/knowledge/search": SEARCH_REPLY}))
    out = tools_by_name(cala)["cala_knowledge_search"].fn({"question": "q"})
    assert out["claims"] == [{"text": "Mistral raised a seed round.", "references": ["r1"]}]
    src = out["sources"][0]
    assert src["id"] == "r1" and len(src["excerpt"]) <= 500
    assert src["origins"] == [{"publisher": "TechCrunch", "title": "Mistral raises", "url": "https://tc.com/m"}]
    assert "content" not in out


def test_a_tool_failure_reaches_the_agent_as_a_tool_error(tmp_path):
    from venus.runner import run_case
    plugin = load_plugin(Path(__file__).parent / "fixtures" / "toy_plugin")
    cala, _ = make(tmp_path, key=None)
    script = [fake_tool_call("cala_knowledge_query", {"question": "never cached"}),
              fake_text(json.dumps({"output": {"label": "positive"}, "sources": []}))]
    model = FakeModel(script)
    result = run_case(plugin, {"text": "great"}, [], model, tools=cala_tools(cala), max_turns=3)
    assert result.output == {"label": "positive"}
    tool_msg = [m for m in model.calls[1]["messages"] if m.get("role") == "tool"][0]
    assert "cala_config_missing" in tool_msg["content"]


# --- gating ------------------------------------------------------------------------------------------------------

def test_cala_flag_defaults_off(toy_plugin_dir, plugin_copy):
    assert load_plugin(toy_plugin_dir).cala_enabled is False
    assert load_plugin(plugin_copy(cala=True)).cala_enabled is True


def test_collect_tools_adds_run_tools_only_in_run_mode_for_opted_in_plugins(tmp_path, toy_plugin_dir, plugin_copy):
    cala, _ = make(tmp_path)
    run_tools = cala_tools(cala)
    off = load_plugin(toy_plugin_dir)
    on = load_plugin(plugin_copy(cala=True))
    names = lambda tools: {t.name for t in tools}
    assert not names(collect_tools(off, {"text": "x"}, run_tools=run_tools)) & names(run_tools)
    assert names(run_tools) <= names(collect_tools(on, {"text": "x"}, run_tools=run_tools))
    assert not names(collect_tools(on, {"text": "x"}, run_tools=run_tools, mode="train")) & names(run_tools)


def test_train_mode_drops_run_only_tools_from_the_plugin_factory(tmp_path, plugin_copy):
    d = plugin_copy(tools="tools:make")
    (d / "tools.py").write_text(
        "def make(input):\n"
        "    f = lambda a: {}\n"
        "    p = {'type': 'object', 'properties': {}}\n"
        "    return [{'name': 'lookup', 'description': 'x', 'parameters': p, 'fn': f, 'run_only': True},\n"
        "            {'name': 'helper', 'description': 'x', 'parameters': p, 'fn': f}]\n")
    plugin = load_plugin(d)
    assert {t.name for t in collect_tools(plugin, {"text": "x"})} == {"lookup", "helper"}
    assert {t.name for t in collect_tools(plugin, {"text": "x"}, mode="train")} == {"helper"}
    with pytest.raises(ValueError):
        collect_tools(plugin, {"text": "x"}, mode="serve")


def test_train_mode_drops_run_only_web_tools_too(toy_plugin_dir):
    sneaky = Tool("cala_like", "x", {"type": "object", "properties": {}}, lambda a: {}, web=True, run_only=True)
    tools = collect_tools(load_plugin(toy_plugin_dir), {"text": "x"}, web_tools=[sneaky], mode="train")
    assert tools == []


def _strategy_dir(tmp_path):
    d = tmp_path / "strategies"
    d.mkdir()
    (d / "toy-set.json").write_text(json.dumps({
        "id": "toy-set", "plugin": "toy-sentiment", "plugin_version": "1.0.0", "status": "validated",
        "base_model": {"model": "fake-model"}, "tendencies": [], "created_at": "2026-11-14T00:00:00Z"}))
    return d


def test_serve_gives_cala_tools_in_run_mode_with_a_fresh_budget_each_run(tmp_path, plugin_copy):
    from venus.serve import Venus
    d = plugin_copy(cala=True)
    models, built = [], []

    def factory(base_model):
        models.append(FakeModel([fake_text(json.dumps({"output": {"label": "positive"}, "sources": []}))]))
        return models[-1]

    def cala_factory():
        built.append(1)
        return cala_tools(make(tmp_path / str(len(built)))[0])
    v = Venus(plugins_dir=d.parent, strategies_dir=_strategy_dir(tmp_path), runs_dir=None, model_factory=factory,
              web_tools=[], env=False, cala_factory=cala_factory)
    req = {"venus_version": "1", "plugin": "toy-sentiment", "mode": "run", "strategy": "toy-set",
           "input": {"text": "great"}}
    assert v.handle(req)["status"] == "ok" and v.handle(req)["status"] == "ok"
    assert len(built) == 2
    offered = {t["function"]["name"] if "function" in t else t["name"] for t in models[0].calls[0]["tools"]}
    assert "cala_knowledge_query" in offered


def test_training_never_offers_cala_tools(tmp_path, plugin_copy):
    from venus.serve import Venus
    d = plugin_copy(cala=True)
    seen = []

    def factory(base_model):
        def reply(messages, tools, tool_choice):
            seen.append({t["function"]["name"] if "function" in t else t["name"] for t in tools or []})
            return fake_text(json.dumps({"output": {"label": "positive"}, "sources": []}))
        return FakeModel(reply)

    def cala_factory():
        raise AssertionError("training must not build Cala tools")
    v = Venus(plugins_dir=d.parent, strategies_dir=_strategy_dir(tmp_path), runs_dir=None, model_factory=factory,
              web_tools=[], env=False, cala_factory=cala_factory)
    resp = v.handle({"venus_version": "1", "plugin": "toy-sentiment", "mode": "training",
                     "cases": [{"id": "c1", "input": {"text": "great"}, "expected": {"label": "positive"}}]})
    assert resp["status"] == "ok", resp
    assert seen and all(not any(n.startswith("cala_") for n in names) for names in seen)


def test_health_reports_cala(tmp_path, toy_plugin_dir, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from venus.serve import Venus, create_app
    v = Venus(plugins_dir=toy_plugin_dir.parent, strategies_dir=tmp_path, runs_dir=None,
              model_factory=lambda b: None, web_tools=[], env=False)
    assert TestClient(create_app(v)).get("/v1/health").json()["cala"] is False
    monkeypatch.setenv("CALA_API_KEY", "k")
    assert TestClient(create_app(v)).get("/v1/health").json()["cala"] is True


# --- phase 8 review fixes ---------------------------------------------------------------------------------------

def test_research_drops_run_only_tools_given_as_dicts(toy_plugin_dir, monkeypatch):
    import venus.training as training
    from venus.request import Case, TrainingRequest
    seen = []

    def spy(plugin, input, tendencies, model, tools=(), **kw):
        seen.append({(t.name if hasattr(t, "name") else t["name"]) for t in tools})
        raise training.VenusError("model_unavailable", "stop here")
    monkeypatch.setattr(training, "run_case", spy)
    plugin = load_plugin(toy_plugin_dir)
    sneaky = {"name": "cala_knowledge_query", "description": "x", "parameters": {"type": "object"},
              "fn": lambda a: {}, "web": True, "run_only": True}
    ok = {"name": "web_search", "description": "x", "parameters": {"type": "object"}, "fn": lambda a: {}, "web": True}
    req = TrainingRequest(plugin=plugin, cases=[Case(id="c1", input={"text": "x"}, expected={"label": "positive"})])
    training.train(req, FakeModel([]), web_tools=[sneaky, ok])
    assert seen and all("cala_knowledge_query" not in names for names in seen)
    assert any("web_search" in names for names in seen)


def test_question_is_sent_and_keyed_as_given_like_the_app_client(tmp_path):
    rec = Recorder({"/v1/knowledge/query": QUERY_REPLY})
    cala, _ = make(tmp_path, rec)
    cala.knowledge_query(" padded question ")
    assert json.loads(rec.requests[0].content)["input"] == " padded question "
    url = "https://api.cala.ai/v1/knowledge/query"
    assert cala.cache_path("POST", url, None, {"input": " padded question ", "return_entities": True}).is_file()
    with pytest.raises(CalaError):
        cala.knowledge_query("   ")


def test_a_bad_call_cap_is_a_server_config_error():
    from venus.serve import http_status
    with pytest.raises(CalaError) as e:
        Cala(api_key="k", environ={"VENUS_CALA_MAX_CALLS": "lots"})
    assert e.value.code == "cala_config_invalid" and http_status(e.value.code) == 500


def test_a_cache_file_that_is_not_an_object_is_a_miss(tmp_path):
    rec = Recorder({"/v1/knowledge/query": QUERY_REPLY})
    cala, _ = make(tmp_path, rec)
    path = cala.cache_path("POST", "https://api.cala.ai/v1/knowledge/query", None,
                           {"input": "q", "return_entities": True})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[1, 2]")
    assert cala.knowledge_query("q") == QUERY_REPLY and len(rec.requests) == 1


def test_cache_files_are_readable_by_other_users(tmp_path):
    import stat
    cala, _ = make(tmp_path, Recorder({"/v1/knowledge/query": QUERY_REPLY}))
    cala.knowledge_query("q")
    [f] = list((tmp_path / "cala").glob("*.json"))
    assert f.stat().st_mode & stat.S_IROTH


# --- phase 9 review: replay must match (H) and client errors are replayed for an hour (B) ---------------------------

def test_a_miss_returns_the_same_key_order_as_the_later_hit(tmp_path):
    rec = Recorder({"/v1/knowledge/query": {"results": [], "entities": [], "content": "x", "a": 1}})
    cala, _ = make(tmp_path, rec)
    first = cala.knowledge_query("q")
    second = cala.knowledge_query("q")
    assert json.dumps(first) == json.dumps(second) and len(rec.requests) == 1


def test_a_client_error_is_replayed_for_an_hour_without_key_or_budget(tmp_path):
    import os
    from venus.cala import FAIL_TTL
    rec = Recorder({"/v1/knowledge/query": {"detail": "no such thing"}}, status=404)
    cala, _ = make(tmp_path, rec, max_calls=1)
    messages = []
    for _ in range(3):
        with pytest.raises(CalaError) as e:
            cala.knowledge_query("q")
        messages.append(e.value.message)
    assert len(rec.requests) == 1 and len(set(messages)) == 1 and "404" in messages[0]
    keyless = Cala(api_key=None, cache_dir=tmp_path / "cala", environ={})
    with pytest.raises(CalaError) as e:
        keyless.knowledge_query("q")
    assert e.value.code == "cala_failed"  # the stored failure, not cala_config_missing
    for f in (tmp_path / "cala").rglob("*.json"):
        old = f.stat().st_mtime - FAIL_TTL - 1
        os.utime(f, (old, old))
    fresh, _ = make(tmp_path, rec, max_calls=1)
    with pytest.raises(CalaError):
        fresh.knowledge_query("q")
    assert len(rec.requests) == 2


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_auth_rate_limit_and_server_errors_are_never_stored(tmp_path, status):
    rec = Recorder({"/v1/knowledge/query": {"detail": "no"}}, status=status)
    cala, _ = make(tmp_path, rec, max_calls=5)
    for _ in range(2):
        with pytest.raises(CalaError):
            cala.knowledge_query("q")
    assert len(rec.requests) == 2 and not list((tmp_path / "cala").rglob("*.json"))


def test_a_stored_failure_is_never_read_as_a_reply_by_the_app_client(tmp_path):
    rec = Recorder({"/v1/knowledge/query": {"detail": "no"}}, status=404)
    cala, _ = make(tmp_path, rec)
    with pytest.raises(CalaError):
        cala.knowledge_query("q")
    assert not list((tmp_path / "cala").glob("*.json"))  # top level holds replies only
    assert list((tmp_path / "cala").rglob("*.json"))
