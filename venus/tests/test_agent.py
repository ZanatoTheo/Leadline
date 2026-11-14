"""The standalone runtime `venus.agent.Agent` (shared_context.md Section 4.2, J1/J2). Offline: FakeModel, toy plugin,
Cala served from a pre-filled cache file (a cache hit needs no key and makes no request)."""
import json
import shutil

import pytest

from venus.agent import Agent, AgentError
from venus.cala import Cala
from venus.errors import ModelError
from venus.fake import FakeModel, fake_text, fake_tool_call

GOOD = json.dumps({"output": {"label": "positive"}, "sources": []})
VERDA = {"model": "nemotron", "provider": "verda"}
ENV = {"VERDA_BASE_URL": "https://verda.example/v1", "VENUS_NEMOTRON_MODEL": "nemotron-3.5-super-vl"}
RESPONSE_KEYS = {"venus_version", "plugin", "mode", "strategy", "status", "outputs", "trace_id", "usage", "base_model",
                 "warnings"}


def strategy(sid, status="validated", base_model=None, settings=None, plugin="toy-sentiment"):
    s = {"id": sid, "plugin": plugin, "plugin_version": "1.0.0", "status": status,
         "base_model": base_model or VERDA, "tendencies": [], "created_at": "2026-11-14T00:00:00Z"}
    if settings is not None:
        s["settings"] = settings
    return s


@pytest.fixture
def root(tmp_path, toy_plugin_dir):
    """An exported-style root: plugins/<id>/ without checker.py, strategies/ with a default and a draft."""
    def make(manifest_changes=None, strategies=None, keep_checker=False):
        plugin = tmp_path / "root" / "plugins" / "toy-sentiment"
        plugin.mkdir(parents=True)
        for f in toy_plugin_dir.iterdir():
            if f.is_file() and (keep_checker or f.name != "checker.py"):
                shutil.copy(f, plugin / f.name)
        manifest = json.loads((plugin / "plugin.json").read_text())
        manifest.update(manifest_changes or {})
        (plugin / "plugin.json").write_text(json.dumps(manifest))
        sdir = tmp_path / "root" / "strategies"
        sdir.mkdir()
        for s in strategies or [strategy("toy-sentiment-default"), strategy("toy-draft", status="draft")]:
            (sdir / f"{s['id']}.json").write_text(json.dumps(s))
        return tmp_path / "root"
    return make


def agent(root_dir, model=None, **kw):
    kw.setdefault("web_tools", [])
    kw.setdefault("cala", False)
    kw.setdefault("environ", dict(ENV))
    return Agent(root_dir, model=model if model is not None else FakeModel([fake_text(GOOD)]), **kw)


# --- 1 + 2: instantiation, run, response shape -------------------------------------------------------------------

def test_run_returns_serve_run_keys_plus_base_model_without_a_checker_file(root):
    resp = agent(root()).run("toy-sentiment", {"text": "great"})
    assert set(resp) == RESPONSE_KEYS, resp
    assert resp["status"] == "ok" and resp["mode"] == "run" and resp["strategy"] == "toy-sentiment-default"
    assert resp["outputs"] == [{"output": {"label": "positive"}, "sources": [], "status": "ok"}]
    assert {"model_calls", "input_tokens", "output_tokens", "web_calls", "cache_hits", "seconds"} <= set(resp["usage"])
    assert resp["base_model"] == {"provider": "injected", "model": "FakeModel"}


def test_trace_id_is_used_as_given_or_made(root):
    a = agent(root(), FakeModel([fake_text(GOOD), fake_text(GOOD)]))
    assert a.run("toy-sentiment", {"text": "great"}, trace_id="t-123")["trace_id"] == "t-123"
    made = a.run("toy-sentiment", {"text": "great"})["trace_id"]
    assert isinstance(made, str) and len(made) == 32


def test_a_named_strategy_is_used(root):
    r = root(strategies=[strategy("toy-sentiment-default"), strategy("toy-other")])
    assert agent(r).run("toy-sentiment", {"text": "great"}, strategy="toy-other")["strategy"] == "toy-other"


def test_plugins_and_strategies_dirs_override_root(root, tmp_path):
    r = root()
    moved = tmp_path / "elsewhere"
    shutil.move(str(r / "strategies"), moved)
    assert agent(None, plugins_dir=r / "plugins", strategies_dir=moved).run("toy-sentiment", {"text": "x"})[
        "status"] == "ok"


def _raise(code):
    def script(messages, tools, tool_choice):
        raise ModelError(code, "boom")
    return script


@pytest.mark.parametrize("call,code", [
    (dict(plugin_id="nope", input_data={"text": "x"}), "plugin_not_found"),
    (dict(plugin_id="toy-sentiment", input_data={"text": "x"}, strategy="missing"), "strategy_not_found"),
    (dict(plugin_id="toy-sentiment", input_data={"text": "x"}, strategy="toy-draft"), "strategy_not_validated"),
    (dict(plugin_id="toy-sentiment", input_data={"wrong": 1}), "input_invalid"),
])
def test_caller_errors_come_back_as_status_error(root, call, code):
    resp = agent(root()).run(**call)
    assert resp["status"] == "error" and resp["outputs"] == [] and resp["error"]["code"] == code
    assert "base_model" not in resp and isinstance(resp["trace_id"], str)


def test_model_and_output_errors_come_back_as_status_error(root):
    r = root()
    assert agent(r, FakeModel(_raise("model_unavailable"))).run("toy-sentiment", {"text": "x"})["error"][
        "code"] == "model_unavailable"
    bad = agent(r, FakeModel([fake_text("not json"), fake_text("still not json")]))
    assert bad.run("toy-sentiment", {"text": "x"})["error"]["code"] == "output_invalid"


def test_missing_root_folders_are_run_errors_not_init_errors(tmp_path):
    a = agent(tmp_path / "absent")
    assert a.run("toy-sentiment", {"text": "x"})["error"]["code"] == "plugin_not_found"


def test_run_rejects_wrong_argument_types_with_type_error(root):
    with pytest.raises(TypeError):
        agent(root()).run("toy-sentiment", "not a dict")


def test_no_web_key_means_no_web_tools_and_a_warning(root):
    a = Agent(root(), model=FakeModel([fake_text(GOOD)]), cala=False, environ=dict(ENV))
    resp = a.run("toy-sentiment", {"text": "x"})
    assert resp["status"] == "ok" and any("web tools off" in w for w in resp["warnings"])


# --- 3: Cala hook ------------------------------------------------------------------------------------------------

def _cala_env(tmp_path):
    cache = tmp_path / "cala-cache"
    reply = {"results": [{"company": "A"}], "entities": [], "content": "x"}
    path = Cala(api_key=None, cache_dir=cache, environ={}).cache_path(
        "POST", "https://api.cala.ai/v1/knowledge/query", None, {"input": "who", "return_entities": True})
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(reply))
    return {**ENV, "VENUS_CALA_CACHE_DIR": str(cache)}


def _cala_script():
    def script(messages, tools, tool_choice):
        if not any(m["role"] == "tool" for m in messages):
            return fake_tool_call("cala_knowledge_query", {"question": "who"})
        return fake_text(GOOD)
    return script


def test_per_run_cala_hook_wins_over_the_default_and_sees_the_reply(root, tmp_path):
    default, per_run = [], []
    a = agent(root({"cala": True}), FakeModel(_cala_script()), cala=True, environ=_cala_env(tmp_path),
              on_cala_result=lambda *args: default.append(args))
    resp = a.run("toy-sentiment", {"text": "x"}, trace_id="t-1",
                 on_cala_result=lambda kind, request, reply: per_run.append((kind, request, reply)))
    assert resp["status"] == "ok", resp
    assert default == [] and len(per_run) == 1
    kind, request, reply = per_run[0]
    assert kind == "knowledge_query" and reply["results"] == [{"company": "A"}] and isinstance(request, dict)


def test_default_cala_hook_is_used_when_run_gives_none(root, tmp_path):
    seen = []
    a = agent(root({"cala": True}), FakeModel(_cala_script()), cala=True, environ=_cala_env(tmp_path),
              on_cala_result=lambda *args: seen.append(args))
    assert a.run("toy-sentiment", {"text": "x"})["status"] == "ok" and len(seen) == 1


def test_a_failing_hook_does_not_fail_the_run(root, tmp_path):
    def boom(*args):
        raise RuntimeError("db down")
    a = agent(root({"cala": True}), FakeModel(_cala_script()), cala=True, environ=_cala_env(tmp_path))
    assert a.run("toy-sentiment", {"text": "x"}, on_cala_result=boom)["status"] == "ok"


def test_cala_false_offers_no_cala_tools(root, tmp_path):
    offered = []

    def script(messages, tools, tool_choice):
        offered.extend(t["function"]["name"] for t in tools or [])
        return fake_text(GOOD)
    agent(root({"cala": True}), FakeModel(script), cala=False, environ=_cala_env(tmp_path)).run(
        "toy-sentiment", {"text": "x"})
    assert not any(name.startswith("cala_") for name in offered)


# --- 4: Verda / NVIDIA: fallback and max_tokens ------------------------------------------------------------------

def factory(primary_script, seen):
    """model_factory: verda -> a model running primary_script; anything else -> a model that answers."""
    def make(base_model):
        seen.append(dict(base_model))
        if base_model.get("provider") == "verda":
            return FakeModel(primary_script)
        return FakeModel([fake_text(GOOD)])
    return make


@pytest.mark.parametrize("code", ["model_unavailable", "model_auth_failed", "model_config_missing",
                                  "request_timeout"])
def test_primary_failure_falls_back_once_and_says_so(root, code):
    seen = []
    a = Agent(root(), model_factory=factory(_raise(code), seen), web_tools=[], cala=False, environ=dict(ENV),
              fallback_base_model={"provider": "nvidia", "model": "nv-model"})
    resp = a.run("toy-sentiment", {"text": "x"})
    assert resp["status"] == "ok", resp
    assert resp["base_model"] == {"provider": "nvidia", "model": "nv-model"}
    assert f"fell back to nvidia: {code}" in resp["warnings"]
    assert [b.get("provider") for b in seen] == ["verda", "nvidia"]


def test_no_fallback_on_output_invalid(root):
    seen = []
    a = Agent(root(), model_factory=factory([fake_text("bad"), fake_text("bad")], seen), web_tools=[], cala=False,
              environ=dict(ENV), fallback_base_model={"provider": "nvidia", "model": "nv-model"})
    assert a.run("toy-sentiment", {"text": "x"})["error"]["code"] == "output_invalid" and len(seen) == 1


def test_primary_success_reports_the_resolved_verda_model(root):
    a = Agent(root(), model_factory=factory([fake_text(GOOD)], []), web_tools=[], cala=False, environ=dict(ENV),
              fallback_base_model=None)
    assert a.run("toy-sentiment", {"text": "x"})["base_model"] == {"provider": "verda",
                                                                    "model": "nemotron-3.5-super-vl"}


def test_fallback_from_env(root):
    seen = []
    env = {**ENV, "VENUS_FALLBACK_PROVIDER": "nvidia", "VENUS_FALLBACK_MODEL": "nv-env"}
    a = Agent(root(), model_factory=factory(_raise("model_unavailable"), seen), web_tools=[], cala=False, environ=env)
    assert a.run("toy-sentiment", {"text": "x"})["base_model"] == {"provider": "nvidia", "model": "nv-env"}


def test_no_fallback_when_env_names_none(root):
    a = Agent(root(), model_factory=factory(_raise("model_unavailable"), []), web_tools=[], cala=False,
              environ=dict(ENV))
    assert a.run("toy-sentiment", {"text": "x"})["error"]["code"] == "model_unavailable"


def test_injected_model_never_falls_back(root):
    a = agent(root(), FakeModel(_raise("model_unavailable")),
              fallback_base_model={"provider": "nvidia", "model": "nv-model"})
    assert a.run("toy-sentiment", {"text": "x"})["error"]["code"] == "model_unavailable"


@pytest.mark.parametrize("env,expected", [({}, 8192), ({"VENUS_MAX_TOKENS": "5000"}, 5000),
                                          ({"VENUS_MAX_TOKENS": "99999"}, 32768),
                                          ({"VENUS_MAX_TOKENS": "lots"}, 8192)])
def test_verda_runs_ask_for_room_to_reason(root, env, expected):
    models = []

    def make(base_model):
        models.append(FakeModel([fake_text(GOOD)]))
        return models[-1]
    Agent(root(), model_factory=make, web_tools=[], cala=False, environ={**ENV, **env},
          fallback_base_model=None).run("toy-sentiment", {"text": "x"})
    assert models[0].calls[0]["max_tokens"] == expected


# --- 5: settings -------------------------------------------------------------------------------------------------

SETTINGS_SCHEMA = {"type": "object", "additionalProperties": False,
                   "properties": {"rules": {"type": "array", "items": {"type": "string"}}}}


def test_settings_returns_the_plugin_settings_of_the_default_strategy(root):
    r = root({"settings_schema": SETTINGS_SCHEMA},
             strategies=[strategy("toy-sentiment-default", settings={"max_turns": 3, "rules": ["a"]}),
                         strategy("toy-draft", status="draft")])
    a = agent(r)
    assert a.settings("toy-sentiment") == {"rules": ["a"]}
    with pytest.raises(AgentError) as e:
        a.settings("toy-sentiment", strategy="toy-draft")
    assert e.value.code == "strategy_not_validated" and e.value.message
    with pytest.raises(AgentError) as e:
        a.settings("nope")
    assert e.value.code == "plugin_not_found"


# --- fallback provider defaults (Claude fallback: no NVIDIA key in this project) ---------------------------------

def test_anthropic_fallback_defaults_to_the_claude_research_preset(root):
    seen = []
    env = {**ENV, "VENUS_FALLBACK_PROVIDER": "anthropic"}
    a = Agent(root(), model_factory=factory(_raise("model_unavailable"), seen), web_tools=[], cala=False, environ=env)
    resp = a.run("toy-sentiment", {"text": "x"})
    assert resp["status"] == "ok", resp
    assert seen[1] == {"provider": "anthropic", "model": "claude-research"}
    assert resp["base_model"] == {"provider": "anthropic", "model": "claude-opus-5-5"}  # the preset's default model
    assert "fell back to anthropic: model_unavailable" in resp["warnings"]


def test_fallback_model_env_wins_over_the_provider_default(root):
    seen = []
    env = {**ENV, "VENUS_FALLBACK_PROVIDER": "anthropic", "VENUS_FALLBACK_MODEL": "claude-fast"}
    Agent(root(), model_factory=factory(_raise("request_timeout"), seen), web_tools=[], cala=False,
          environ=env).run("toy-sentiment", {"text": "x"})
    assert seen[1] == {"provider": "anthropic", "model": "claude-fast"}


def test_fallback_defaults_per_provider():
    from venus.agent.core import fallback_from
    assert fallback_from({}) is None
    assert fallback_from({"VENUS_FALLBACK_PROVIDER": "nvidia"}) == {"provider": "nvidia",
                                                                     "model": "nvidia/nemotron-3.5-lightning-30b-a3b"}
    assert fallback_from({"VENUS_FALLBACK_PROVIDER": "anthropic"})["model"] == "claude-research"


# --- review fixes: a failing fallback, a missing anthropic package, provider defaults ------------------------------

def test_a_failing_fallback_keeps_the_primary_error_and_says_why(root):
    def make(base_model):
        code = "model_unavailable" if base_model.get("provider") == "verda" else "model_auth_failed"
        return FakeModel(_raise(code))
    env = {**ENV, "VENUS_FALLBACK_PROVIDER": "anthropic"}
    resp = Agent(root(), model_factory=make, web_tools=[], cala=False, environ=env).run("toy-sentiment", {"text": "x"})
    assert resp["status"] == "error" and resp["error"]["code"] == "model_unavailable"
    assert "fell back to anthropic: model_unavailable" in resp["warnings"]
    assert any(w.startswith("fallback to anthropic failed: model_auth_failed") for w in resp["warnings"])


def _block_anthropic(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "anthropic", None)  # `import anthropic` -> ImportError
    for name in ("venus.agent.anthropic_client", "venus.anthropic_client"):
        monkeypatch.delitem(sys.modules, name, raising=False)


def test_missing_anthropic_package_is_a_model_config_error(monkeypatch):
    from venus.agent.core import default_model_factory
    _block_anthropic(monkeypatch)
    with pytest.raises(ModelError) as e:
        default_model_factory(environ={"ANTHROPIC_API_KEY": "k"})({"provider": "anthropic", "model": "claude-research"})
    assert e.value.code == "model_config_missing" and "anthropic" in e.value.message


def test_missing_anthropic_package_on_fallback_returns_an_error_not_a_raise(root, monkeypatch):
    from venus.agent.core import default_model_factory
    _block_anthropic(monkeypatch)
    env = {**ENV, "VENUS_FALLBACK_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "k"}
    real = default_model_factory(environ=env)

    def make(base_model):
        return FakeModel(_raise("model_unavailable")) if base_model.get("provider") == "verda" else real(base_model)
    resp = Agent(root(), model_factory=make, web_tools=[], cala=False, environ=env).run("toy-sentiment", {"text": "x"})
    assert resp["status"] == "error" and resp["error"]["code"] == "model_unavailable"
    assert any("model_config_missing" in w for w in resp["warnings"])


def test_fallback_defaults_cover_every_preset_provider_and_ignore_case():
    from venus.agent.core import fallback_from
    assert fallback_from({"VENUS_FALLBACK_PROVIDER": "Anthropic"}) == {"provider": "anthropic",
                                                                        "model": "claude-research"}
    assert fallback_from({"VENUS_FALLBACK_PROVIDER": "meta"})["model"] == "meta"
    assert fallback_from({"VENUS_FALLBACK_PROVIDER": "gemini"})["model"] == "gemini"
