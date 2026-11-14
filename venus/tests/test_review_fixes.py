"""Regression tests for the four bugs the first full review found (2026-11-14). Each test failed before its fix."""
import json
import shutil

import httpx
import pytest
from jsonschema import Draft202012Validator

from venus import runner
from venus.budget import Budget
from venus.config import ModelSpec
from venus.errors import BudgetExceeded, PluginError
from venus.fake import FakeModel, fake_text
from venus.models import ModelClient, ModelReply, ToolCall
from venus.plugin import load_plugin
from venus.runner import run_case
from venus.schemas import load_schema
from venus.serve import Venus
from venus.tools import Tool, as_tool

SPEC = ModelSpec(provider="verda", base_url="https://verda.test/v1", model="m-1", key_env="VERDA_API_KEY")
QUERY = {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}


def valid(resp):
    errors = list(Draft202012Validator(load_schema("response")).iter_errors(resp))
    assert errors == [], [e.message for e in errors]
    return resp


# --- bug 1: a non-string tool name must be a PluginError, not a TypeError -------------------------------------------

@pytest.mark.parametrize("name", [5, 1.5, ["a"], {"a": 1}])
def test_non_string_tool_name_is_plugin_error(name):
    with pytest.raises(PluginError) as e:
        as_tool({"name": name, "description": "d", "fn": lambda a: 1})
    assert e.value.code == "plugin_tools_failed"


# --- bug 2: retries must respect the seconds cap; the model timeout must fit Verda's 60 s ----------------------------

class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def test_retries_stop_when_the_seconds_budget_is_spent():
    clock = FakeClock()
    requests = []

    def server(request):
        requests.append(1)
        return httpx.Response(500, json={"error": {"message": "boom"}})

    budget = Budget(max_seconds=10, clock=clock)
    model = ModelClient(SPEC, api_key="k", budget=budget, sleep=clock.sleep, max_attempts=5,
                        http_client=httpx.Client(transport=httpx.MockTransport(server)))
    with pytest.raises(BudgetExceeded):
        model.chat([{"role": "user", "content": "hi"}])
    assert len(requests) < 5, f"made all {len(requests)} attempts although the budget was spent"


def test_model_timeout_defaults_to_60s_and_can_be_set_by_env():
    # NVIDIA: Verda clients have a 120 s floor on the env value (test_models.py, phase 10)
    nv = ModelSpec(provider="nvidia", base_url="https://nv.test/v1", model="m-1", key_env="NVIDIA_API_KEY")
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={}))
    default = ModelClient(nv, api_key="k", environ={}, http_client=httpx.Client(transport=transport))
    assert default._client.timeout == 60.0
    custom = ModelClient(nv, api_key="k", environ={"VENUS_MODEL_TIMEOUT": "25"},
                         http_client=httpx.Client(transport=transport))
    assert custom._client.timeout == 25.0
    explicit = ModelClient(SPEC, api_key="k", timeout=7.0, environ={"VENUS_MODEL_TIMEOUT": "25"},
                           http_client=httpx.Client(transport=transport))
    assert explicit._client.timeout == 7.0
    bad = ModelClient(nv, api_key="k", environ={"VENUS_MODEL_TIMEOUT": "soon"},
                      http_client=httpx.Client(transport=transport))
    assert bad._client.timeout == 60.0


# --- bug 3: cap tool calls per reply, and web calls per run -----------------------------------------------------------

@pytest.fixture
def plugin(toy_plugin_dir):
    return load_plugin(toy_plugin_dir)


def many_calls(n):
    calls = [ToolCall(id=f"c{i}", name="web_search", arguments={"query": f"q{i}"}) for i in range(n)]
    return ModelReply(text=None, tool_calls=calls, model="fake-model", finish_reason="tool_calls")


def final(label):
    return fake_text(json.dumps({"output": {"label": label}, "sources": []}), input_tokens=1, output_tokens=1)


def test_tool_calls_in_one_reply_are_capped(plugin):
    ran = []
    tool = Tool("web_search", "Search.", QUERY, lambda a: ran.append(a) or {"results": []}, web=True)
    n = runner.MAX_TOOL_CALLS_PER_TURN + 7
    model = FakeModel([many_calls(n), final("positive")])
    result = run_case(plugin, {"text": "great"}, [], model, tools=[tool])
    assert len(ran) == runner.MAX_TOOL_CALLS_PER_TURN
    assert result.usage["web_calls"] == runner.MAX_TOOL_CALLS_PER_TURN
    # every call id still gets an answer, or the provider rejects the next request
    answered = [m["tool_call_id"] for m in model.calls[1]["messages"] if m["role"] == "tool"]
    assert answered == [f"c{i}" for i in range(n)]
    assert any("skipped" in w for w in result.warnings)


def test_web_calls_per_run_are_capped(plugin, monkeypatch):
    monkeypatch.setattr(runner, "MAX_TOOL_CALLS_PER_TURN", 10)
    monkeypatch.setattr(runner, "MAX_WEB_CALLS", 4)
    ran = []
    tool = Tool("web_search", "Search.", QUERY, lambda a: ran.append(a) or {"results": []}, web=True)
    model = FakeModel([many_calls(3), many_calls(3), final("positive")])
    result = run_case(plugin, {"text": "great"}, [], model, tools=[tool])
    assert len(ran) == 4 and result.usage["web_calls"] == 4
    assert any("web call limit" in w for w in result.warnings)


# --- bug 4: disk and file-encoding errors must come back as error responses, not escape handle() --------------------

def make_venus(toy_plugin_dir, strategies_dir, runs_dir, script):
    return Venus(plugins_dir=toy_plugin_dir.parent, strategies_dir=strategies_dir, runs_dir=runs_dir,
                 model_factory=lambda base: FakeModel(script), web_tools=[], env=False)


def test_unwritable_runs_folder_gives_an_error_response(toy_plugin_dir, strategies_dir, tmp_path, example):
    not_a_folder = tmp_path / "runs"
    not_a_folder.write_text("a file where a folder should be")
    v = make_venus(toy_plugin_dir, strategies_dir, not_a_folder, [final("positive"), final("negative")])
    resp = valid(v.handle(example("request_training.json")))
    assert resp["status"] == "error" and resp["error"]["code"] == "storage_failed"


def test_strategy_file_with_bad_encoding_gives_an_error_response(toy_plugin_dir, strategies_dir, tmp_path):
    folder = tmp_path / "strategies"
    shutil.copytree(strategies_dir, folder)
    (folder / "garbled.json").write_bytes(b"\xff\xfe{\x00 not utf-8")
    v = make_venus(toy_plugin_dir, folder, tmp_path / "runs", [final("positive")])
    raw = {"venus_version": "1", "plugin": "toy-sentiment", "mode": "run", "strategy": "garbled",
           "input": {"text": "great"}}
    resp = valid(v.handle(raw))
    assert resp["status"] == "error" and resp["error"]["code"] == "storage_failed"


def test_storage_failed_maps_to_http_500():
    from venus.serve import http_status
    assert http_status("storage_failed") == 500
