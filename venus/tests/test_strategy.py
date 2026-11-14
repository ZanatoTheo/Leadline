import pytest

from venus.errors import StrategyError
from venus.strategy import StrategyStore


def test_validated_strategy_loads(strategies_dir):
    s = StrategyStore(strategies_dir).get("toy-validated")
    assert s.plugin == "toy-sentiment"
    assert s.is_validated
    assert s.tendencies[0].text.startswith("Treat")
    assert s.base_model["model"] == "fake-model"


def test_draft_is_not_validated(strategies_dir):
    assert not StrategyStore(strategies_dir).get("toy-draft").is_validated


def test_unknown_strategy(strategies_dir):
    with pytest.raises(StrategyError) as e:
        StrategyStore(strategies_dir).get("nope")
    assert e.value.code == "strategy_not_found"


def test_broken_strategy_file(strategies_dir):
    with pytest.raises(StrategyError) as e:
        StrategyStore(strategies_dir).get("broken")
    assert e.value.code == "strategy_invalid"


def test_id_cannot_escape_folder(strategies_dir):
    with pytest.raises(StrategyError) as e:
        StrategyStore(strategies_dir).get("../toy_plugin/plugin")
    assert e.value.code == "strategy_not_found"


def test_strategy_schema_accepts_every_configured_provider():
    """A provider added to config.PROVIDERS must be usable in a strategy's base_model (training saves drafts with
    the training provider, e.g. anthropic)."""
    from venus.config import PROVIDERS
    from venus.schemas import load_schema
    enum = load_schema("strategy")["properties"]["base_model"]["properties"]["provider"]["enum"]
    assert set(enum) == set(PROVIDERS)


# --- settings: typed knobs a strategy carries (phase 6) ----------------------------------------------------------

import json as _json  # noqa: E402

from venus.errors import PluginError  # noqa: E402
from venus.plugin import load_plugin  # noqa: E402
from venus.request import check_request  # noqa: E402

PLUGIN_SETTINGS = {"type": "object", "additionalProperties": False, "properties": {
    "rules": {"type": "array", "items": {"enum": ["stage", "sector"]}, "uniqueItems": True},
    "min_share": {"type": "number", "minimum": 0, "maximum": 0.5}}}


def _strategy_dir(tmp_path, **extra):
    d = tmp_path / "strategies"
    d.mkdir(parents=True, exist_ok=True)
    data = {"id": "toy-set", "plugin": "toy-sentiment", "plugin_version": "1.0.0", "status": "validated",
            "base_model": {"model": "fake-model"}, "tendencies": [], "created_at": "2026-11-14T00:00:00Z", **extra}
    (d / "toy-set.json").write_text(_json.dumps(data))
    return d


def _run(plugin, d):
    return check_request({"venus_version": "1", "plugin": "toy-sentiment", "mode": "run", "strategy": "toy-set",
                          "input": {"text": "great"}}, {plugin.name: plugin}, StrategyStore(d))


def test_settings_load_and_split(tmp_path):
    d = _strategy_dir(tmp_path, settings={"max_turns": 3, "max_web_calls": 1, "rules": ["stage"]})
    s = StrategyStore(d).get("toy-set")
    assert s.settings == {"max_turns": 3, "max_web_calls": 1, "rules": ["stage"]}
    assert s.core_settings == {"max_turns": 3, "max_web_calls": 1} and s.plugin_settings == {"rules": ["stage"]}
    assert StrategyStore(_strategy_dir(tmp_path / "b")).get("toy-set").settings == {}  # optional


def test_settings_must_be_an_object(tmp_path):
    with pytest.raises(StrategyError) as e:
        StrategyStore(_strategy_dir(tmp_path, settings="fast")).get("toy-set")
    assert e.value.code == "strategy_invalid"


def test_plugin_settings_schema_inline(plugin_copy):
    assert load_plugin(plugin_copy(settings_schema=PLUGIN_SETTINGS)).settings_schema == PLUGIN_SETTINGS


def test_plugin_settings_schema_file(plugin_copy):
    d = plugin_copy(settings_schema="settings.schema.json")
    (d / "settings.schema.json").write_text(_json.dumps(PLUGIN_SETTINGS))
    assert load_plugin(d).settings_schema == PLUGIN_SETTINGS


def test_bad_plugin_settings_schema_is_refused(plugin_copy):
    with pytest.raises(PluginError) as e:
        load_plugin(plugin_copy(settings_schema={"type": "nonsense"}))
    assert e.value.code == "plugin_schema_invalid"


@pytest.mark.parametrize("settings,path", [
    ({"temperature": 0.2}, "settings"),  # unknown key, plugin declares no settings
    ({"max_turns": "3"}, "settings.max_turns"),
    ({"max_turns": 0}, "settings.max_turns"),
    ({"max_web_calls": -1}, "settings.max_web_calls"),
])
def test_unknown_or_wrong_settings_are_strategy_invalid(tmp_path, toy_plugin_dir, settings, path):
    with pytest.raises(StrategyError) as e:
        _run(load_plugin(toy_plugin_dir), _strategy_dir(tmp_path, settings=settings))
    assert e.value.code == "strategy_invalid" and (e.value.path or "").startswith(path)


@pytest.mark.parametrize("settings", [{"rules": ["stage", "stage"]}, {"min_share": 0.9}, {"colour": "red"}])
def test_plugin_settings_are_checked_against_its_schema(tmp_path, plugin_copy, settings):
    plugin = load_plugin(plugin_copy(settings_schema=PLUGIN_SETTINGS))
    with pytest.raises(StrategyError) as e:
        _run(plugin, _strategy_dir(tmp_path, settings=settings))
    assert e.value.code == "strategy_invalid"


def test_valid_settings_pass(tmp_path, plugin_copy):
    plugin = load_plugin(plugin_copy(settings_schema=PLUGIN_SETTINGS))
    req = _run(plugin, _strategy_dir(tmp_path, settings={"max_turns": 2, "rules": ["sector"], "min_share": 0.1}))
    assert req.strategy.plugin_settings == {"rules": ["sector"], "min_share": 0.1}


def test_venus_applies_core_settings_in_run_mode(tmp_path, toy_plugin_dir):
    from venus.fake import FakeModel, fake_text
    from venus.serve import Venus
    from venus.tools import Tool
    models = []

    def factory(base_model):
        models.append(FakeModel([fake_text(_json.dumps({"output": {"label": "positive"},
                                                         "sources": ["https://a.example"]}))]))
        return models[-1]
    search = Tool("web_search", "Search.", {"type": "object", "properties": {"query": {"type": "string"}}},
                  lambda a: {"results": []}, web=True)
    d = _strategy_dir(tmp_path, settings={"max_turns": 1})
    v = Venus(plugins_dir=toy_plugin_dir.parent, strategies_dir=d, runs_dir=None, model_factory=factory,
              web_tools=[search], env=False)
    resp = v.handle({"venus_version": "1", "plugin": "toy-sentiment", "mode": "run", "strategy": "toy-set",
                     "input": {"text": "great"}})
    assert resp["status"] == "ok", resp
    assert models[0].calls[0]["tool_choice"] == "none"  # one turn: answer at once, no forced search


# --- phase 6 review fixes ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("settings", [{"max_turns": True}, {"max_turns": 2.0}, {"max_web_calls": 1.0}])
def test_core_settings_must_be_whole_numbers_not_bools_or_floats(tmp_path, toy_plugin_dir, settings):
    with pytest.raises(StrategyError) as e:
        _run(load_plugin(toy_plugin_dir), _strategy_dir(tmp_path, settings=settings))
    assert e.value.code == "strategy_invalid"


@pytest.mark.parametrize("schema", [
    {"type": "object", "additionalProperties": False, "properties": {"max_turns": {"type": "integer"}}},  # core key
    {"type": "object", "properties": {"rules": {"type": "array"}}},  # extra keys not refused
    {"type": "object", "additionalProperties": False},  # no properties
    {"$ref": "https://example.com/s.json"},
])
def test_plugin_settings_schema_must_be_a_closed_object_without_core_keys(plugin_copy, schema):
    with pytest.raises(PluginError) as e:
        load_plugin(plugin_copy(settings_schema=schema))
    assert e.value.code == "plugin_schema_invalid"


def test_a_settings_schema_that_cannot_resolve_is_strategy_invalid(tmp_path, plugin_copy):
    schema = {"type": "object", "additionalProperties": False,
              "properties": {"rules": {"$ref": "https://example.invalid/rules.json"}}}
    plugin = load_plugin(plugin_copy(settings_schema=schema))
    with pytest.raises(StrategyError) as e:
        _run(plugin, _strategy_dir(tmp_path, settings={"rules": ["x"]}))
    assert e.value.code == "strategy_invalid"


def _venus_with(tmp_path, plugin_dir, settings, script, search_calls):
    from venus.fake import FakeModel
    from venus.serve import Venus
    from venus.tools import Tool
    models = []

    def factory(base_model):
        models.append(FakeModel(script))
        return models[-1]
    search = Tool("web_search", "Search.", {"type": "object", "properties": {"query": {"type": "string"}}},
                  lambda a: search_calls.append(a) or {"results": [{"url": "https://a.example"}]}, web=True)
    v = Venus(plugins_dir=plugin_dir.parent, strategies_dir=_strategy_dir(tmp_path, settings=settings),
              runs_dir=None, model_factory=factory, web_tools=[search], env=False)
    resp = v.handle({"venus_version": "1", "plugin": "toy-sentiment", "mode": "run", "strategy": "toy-set",
                     "input": {"text": "great"}})
    return resp, models


def test_max_web_calls_is_enforced_in_run_mode(tmp_path, toy_plugin_dir):
    from venus.fake import fake_text, fake_tool_call
    calls = []
    script = [fake_tool_call("web_search", {"query": "x"}),
              fake_text(_json.dumps({"output": {"label": "positive"}, "sources": []}))]
    resp, _ = _venus_with(tmp_path, toy_plugin_dir, {"max_web_calls": 0}, script, calls)
    assert resp["status"] == "ok" and calls == [] and resp["usage"]["web_calls"] == 0


def test_plugin_settings_reach_the_plugin_tools_factory(tmp_path, plugin_copy):
    from venus.fake import fake_text
    d = plugin_copy(tools="tools:make", settings_schema=PLUGIN_SETTINGS)
    (d / "tools.py").write_text(
        "import json\n"
        "def make(input, settings=None):\n"
        "    return [{'name': 'echo', 'description': 'settings=' + json.dumps(settings, sort_keys=True),\n"
        "             'parameters': {'type': 'object', 'properties': {}}, 'fn': lambda a: {}}]\n")
    script = [fake_text(_json.dumps({"output": {"label": "positive"}, "sources": ["https://a.example"]}))]
    resp, models = _venus_with(tmp_path, d, {"rules": ["stage"], "max_turns": 2}, script, [])
    assert resp["status"] == "ok", resp
    described = [t["function"]["description"] for t in models[0].calls[0]["tools"]]
    assert 'settings={"rules": ["stage"]}' in described  # plugin keys only, core keys stay with Venus
