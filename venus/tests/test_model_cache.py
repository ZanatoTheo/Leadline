import json

import httpx

from venus.budget import Budget
from venus.cache import DiskCache, model_cache_from_env
from venus.config import ModelSpec
from venus.fake import FakeModel, fake_text, fake_tool_call
from venus.models import CachedModel, ModelClient, ModelReply, ToolCall, function_tool
from venus.schemas import load_schema
from venus.serve import Venus, default_model_factory

SPEC = ModelSpec(provider="verda", base_url="https://verda.test/v1", model="m-1", key_env="VERDA_API_KEY")
MSG = [{"role": "user", "content": "hi"}]
SEARCH = function_tool("web_search", "Search.", {"type": "object", "properties": {"query": {"type": "string"}}})


def cached(tmp_path, script, budget=None, model_name="m-1"):
    inner = FakeModel(script, budget=budget)
    return CachedModel(inner, DiskCache(tmp_path / "models"), provider="verda", model=model_name), inner


def test_same_request_twice_calls_the_model_once(tmp_path):
    model, inner = cached(tmp_path, [fake_text("a", 10, 5), fake_text("b")])
    first = model.chat(MSG, seed=1)
    second = model.chat(MSG, seed=1)
    assert len(inner.calls) == 1
    assert first.cached is False and second.cached is True
    assert second.text == "a"
    assert second.usage == {"input_tokens": 0, "output_tokens": 0}  # a hit costs nothing


def test_budget_is_charged_once(tmp_path):
    budget = Budget(max_model_calls=5)
    model, _ = cached(tmp_path, [fake_text("a", 10, 5)], budget=budget)
    model.chat(MSG, seed=1)
    model.chat(MSG, seed=1)
    assert budget.spent()["model_calls"] == 1


def test_a_hit_still_works_when_the_budget_is_spent(tmp_path):
    budget = Budget(max_model_calls=1)
    model, _ = cached(tmp_path, [fake_text("a")], budget=budget)
    model.chat(MSG, seed=1)
    assert model.chat(MSG, seed=1).text == "a"


def test_temperature_above_zero_without_a_seed_is_not_cached(tmp_path):
    model, inner = cached(tmp_path, [fake_text("a"), fake_text("b")])
    assert model.chat(MSG, temperature=0.7).text == "a"
    assert model.chat(MSG, temperature=0.7).text == "b"
    assert len(inner.calls) == 2


def test_temperature_above_zero_with_a_seed_is_cached(tmp_path):
    model, inner = cached(tmp_path, [fake_text("a"), fake_text("b")])
    model.chat(MSG, temperature=0.7, seed=3)
    assert model.chat(MSG, temperature=0.7, seed=3).text == "a"
    assert len(inner.calls) == 1


def test_temperature_zero_is_injected_when_neither_temperature_nor_seed_is_given(tmp_path):
    model, inner = cached(tmp_path, [fake_text("a")])
    model.chat(MSG)
    assert inner.calls[0]["temperature"] == 0
    assert model.chat(MSG).cached is True


def test_different_model_messages_tools_or_seed_miss(tmp_path):
    cache_dir = tmp_path / "models"
    a = CachedModel(FakeModel([fake_text("a")] * 5), DiskCache(cache_dir), provider="verda", model="m-1")
    b = CachedModel(FakeModel([fake_text("b")] * 5), DiskCache(cache_dir), provider="verda", model="m-2")
    c = CachedModel(FakeModel([fake_text("c")] * 5), DiskCache(cache_dir), provider="nvidia", model="m-1")
    assert a.chat(MSG, seed=1).text == "a"
    assert b.chat(MSG, seed=1).text == "b"  # other model id
    assert c.chat(MSG, seed=1).text == "c"  # other provider
    assert a.chat([{"role": "user", "content": "bye"}], seed=1).text == "a"  # other messages (a miss: fresh call)
    assert a.chat(MSG, seed=2).cached is False  # other seed
    assert a.chat(MSG, tools=[SEARCH], seed=1).cached is False  # other tools
    assert a.chat(MSG, seed=1).cached is True


def test_tool_call_replies_round_trip(tmp_path):
    model, _ = cached(tmp_path, [fake_tool_call("web_search", {"query": "x"}, id="call_1")])
    model.chat(MSG, tools=[SEARCH], tool_choice="required", seed=1)
    hit = model.chat(MSG, tools=[SEARCH], tool_choice="required", seed=1)
    assert hit.cached is True and hit.text is None
    assert hit.tool_calls == [ToolCall(id="call_1", name="web_search", arguments={"query": "x"})]
    assert hit.finish_reason == "tool_calls" and hit.model == "fake-model"


def test_replies_with_a_parse_error_or_cut_off_text_or_nothing_are_not_cached(tmp_path):
    bad_call = ModelReply(text=None, tool_calls=[ToolCall("c1", "web_search", None, "arguments are not valid JSON")])
    cut = ModelReply(text="half an ans", finish_reason="length")
    empty = ModelReply(text=None)
    model, inner = cached(tmp_path, [bad_call, bad_call, cut, cut, empty, empty])
    for _ in range(2):
        model.chat(MSG, seed=1)
    assert len(inner.calls) == 2
    model.chat([{"role": "user", "content": "2"}], seed=1)
    model.chat([{"role": "user", "content": "2"}], seed=1)
    model.chat([{"role": "user", "content": "3"}], seed=1)
    model.chat([{"role": "user", "content": "3"}], seed=1)
    assert len(inner.calls) == 6


def test_a_damaged_entry_is_a_miss(tmp_path):
    model, inner = cached(tmp_path, [fake_text("a"), fake_text("b")])
    model.chat(MSG, seed=1)
    (entry,) = (tmp_path / "models").glob("*.json")
    entry.write_text(json.dumps({"t": 1.0, "v": {"text": 5, "tool_calls": "no"}}))
    assert model.chat(MSG, seed=1).text == "b"
    assert len(inner.calls) == 2


def test_cache_survives_a_new_wrapper_and_serves_a_real_client(tmp_path):
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={
            "id": "c", "object": "chat.completion", "created": 0, "model": "m-1",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "hello"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 3, "total_tokens": 14}})

    def make():
        real = ModelClient(SPEC, api_key="k", http_client=httpx.Client(transport=httpx.MockTransport(handler)))
        return CachedModel(real, DiskCache(tmp_path / "models"))  # provider and model come from `real.spec`

    assert make().chat(MSG).text == "hello"
    assert make().chat(MSG).cached is True
    assert len(seen) == 1 and seen[0]["temperature"] == 0


def test_model_cache_from_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert model_cache_from_env({}) is None  # off unless asked
    assert model_cache_from_env({"VENUS_MODEL_CACHE": "0"}) is None
    on = model_cache_from_env({"VENUS_MODEL_CACHE": "1"})
    assert on.directory == tmp_path / ".venus_cache" / "models"
    custom = model_cache_from_env({"VENUS_MODEL_CACHE": "1", "VENUS_CACHE_DIR": str(tmp_path / "x")})
    assert custom.directory == tmp_path / "x" / "models"
    assert model_cache_from_env({"VENUS_MODEL_CACHE": "1", "VENUS_CACHE_DIR": "off"}) is None


def test_factory_wraps_the_client_only_when_the_flag_is_set(tmp_path):
    base = {"model": "m-1", "provider": "verda"}
    plain = {"VERDA_API_KEY": "k", "VERDA_BASE_URL": "https://verda.test/v1"}
    env = {**plain, "VENUS_MODEL_CACHE": "1", "VENUS_CACHE_DIR": str(tmp_path / "c")}
    wrapped = default_model_factory(environ=env)(base)
    assert isinstance(wrapped, CachedModel) and wrapped.budget is not None and wrapped.model == "m-1"
    assert isinstance(default_model_factory(environ=plain)(base), ModelClient)


def test_response_schema_accepts_cache_hits():
    import jsonschema
    usage = {"model_calls": 1, "input_tokens": 1, "output_tokens": 1, "web_calls": 0, "cache_hits": 2, "seconds": 0.1}
    schema = load_schema("response")["properties"]["usage"]
    jsonschema.validate(usage, schema)


def test_handle_reports_cache_hits(tmp_path, toy_plugin_dir, strategies_dir):
    cache = DiskCache(tmp_path / "models")
    answer = fake_text(json.dumps({"output": {"label": "positive"}, "sources": []}), 10, 5)

    def factory(base_model):
        return CachedModel(FakeModel([answer]), cache, provider="verda", model="m-1")

    venus = Venus(plugins_dir=toy_plugin_dir.parent, strategies_dir=strategies_dir, runs_dir=tmp_path / "runs",
                  model_factory=factory, web_tools=[], env=False)
    request = {"venus_version": "1", "plugin": "toy-sentiment", "mode": "run", "strategy": "toy-validated",
               "input": {"text": "great"}}
    first, second = venus.handle(request), venus.handle(request)
    assert first["usage"]["cache_hits"] == 0 and first["usage"]["model_calls"] == 1
    assert second["status"] == "ok"
    assert second["usage"]["cache_hits"] == 1 and second["usage"]["model_calls"] == 0
    assert second["usage"]["input_tokens"] == 0


# --- review fixes -------------------------------------------------------------------------------------------------

def _client(base_url, seen):
    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, json={
            "id": "c", "object": "chat.completion", "created": 0, "model": "m-1",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": base_url}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})
    spec = ModelSpec(provider="verda", base_url=base_url, model="m-1", key_env="VERDA_API_KEY")
    return ModelClient(spec, api_key="k", http_client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_a_different_endpoint_is_a_miss(tmp_path):
    seen = []
    cache = DiskCache(tmp_path / "models")
    assert CachedModel(_client("https://host-a.test/v1", seen), cache).chat(MSG).text == "https://host-a.test/v1"
    b = CachedModel(_client("https://host-b.test/v1", seen), cache).chat(MSG)
    assert b.cached is False and b.text == "https://host-b.test/v1" and len(seen) == 2


def test_wrapper_exposes_the_inner_spec(tmp_path):
    real = _client("https://host-a.test/v1", [])
    assert CachedModel(real, DiskCache(tmp_path)).spec is real.spec


def test_an_unusable_cache_folder_does_not_lose_the_reply(tmp_path):
    blocker = tmp_path / "afile"
    blocker.write_text("x")
    model, inner = cached(tmp_path, [fake_text("a"), fake_text("b")])
    model.cache = DiskCache(blocker)  # a file where the folder should be: reads miss, writes raise OSError
    assert model.chat(MSG, seed=1).text == "a"
    assert model.chat(MSG, seed=1).text == "b"


def _toy(toy_plugin_dir):
    from venus.plugin import load_plugin
    return load_plugin(toy_plugin_dir)


GOOD = json.dumps({"output": {"label": "positive"}, "sources": []})


def test_run_case_counts_hits_apart_from_calls(tmp_path, toy_plugin_dir):
    from venus.runner import run_case
    plugin, cache = _toy(toy_plugin_dir), DiskCache(tmp_path / "models")
    first = run_case(plugin, {"text": "great"}, [], CachedModel(FakeModel([fake_text(GOOD, 10, 5)]), cache))
    second = run_case(plugin, {"text": "great"}, [], CachedModel(FakeModel([]), cache))
    assert (first.usage["model_calls"], first.usage["cache_hits"]) == (1, 0)
    assert (second.usage["model_calls"], second.usage["cache_hits"], second.usage["input_tokens"]) == (0, 1, 0)


def test_a_bad_answer_fixed_by_the_repair_is_kept_so_a_rerun_replays_both(tmp_path, toy_plugin_dir):
    """Phase 9 live run: deleting the bad answer made the rerun ask the model again at that slot, and a
    non-deterministic model then took another path. Bad answer + good repair are now both kept."""
    from venus.runner import run_case
    plugin, cache = _toy(toy_plugin_dir), DiskCache(tmp_path / "models")
    first = run_case(plugin, {"text": "great"}, [],
                     CachedModel(FakeModel([fake_text("not json"), fake_text(GOOD)]), cache))
    inner = FakeModel([])
    again = run_case(plugin, {"text": "great"}, [], CachedModel(inner, cache))
    assert inner.calls == [] and again.usage["cache_hits"] == 2 and again.usage["model_calls"] == 0
    assert again.output == first.output == {"label": "positive"}


def test_when_the_repair_fails_too_both_answers_are_dropped(tmp_path, toy_plugin_dir):
    import pytest

    from venus.errors import InputError
    from venus.runner import run_case
    plugin, cache = _toy(toy_plugin_dir), DiskCache(tmp_path / "models")
    with pytest.raises(InputError):
        run_case(plugin, {"text": "great"}, [],
                 CachedModel(FakeModel([fake_text("not json"), fake_text("still not json")]), cache))
    assert not list((tmp_path / "models").glob("*.json"))  # nothing bad is replayed later
    inner = FakeModel([fake_text(GOOD)])
    again = run_case(plugin, {"text": "great"}, [], CachedModel(inner, cache))
    assert len(inner.calls) == 1 and again.output == {"label": "positive"}


def test_a_failed_run_keeps_its_usage(toy_plugin_dir):
    import pytest
    from venus.errors import VenusError
    from venus.runner import run_case
    with pytest.raises(VenusError) as err:
        run_case(_toy(toy_plugin_dir), {"text": "x"}, [], FakeModel([fake_text("bad", 4, 2), fake_text("bad", 4, 2)]))
    assert err.value.code == "output_invalid"
    assert err.value.usage["model_calls"] == 2 and err.value.usage["input_tokens"] == 8


def test_training_counts_calls_of_failed_cases(toy_plugin_dir, strategies_dir, example):
    from venus.plugin import load_plugin
    from venus.request import check_request
    from venus.strategy import StrategyStore
    from venus.training import train
    plugin = load_plugin(toy_plugin_dir)
    req = check_request(example("request_training.json"), {plugin.name: plugin}, StrategyStore(strategies_dir))
    model = FakeModel(lambda messages, tools, tool_choice: fake_text("not json", 1, 1))
    resp = train(req, model)
    assert resp["status"] == "error"
    assert resp["usage"]["model_calls"] == len(model.calls) > 0
    assert resp["usage"]["cache_hits"] == 0


def test_training_counts_a_case_once_when_scoring_fails(toy_plugin_dir, strategies_dir, example):
    from venus.plugin import load_plugin
    from venus.request import check_request
    from venus.strategy import StrategyStore
    from venus.training import train
    plugin = load_plugin(toy_plugin_dir)

    def broken(input, output, expected):
        raise RuntimeError("checker bug")
    import dataclasses
    plugin = dataclasses.replace(plugin, checker=broken)
    req = check_request(example("request_training.json"), {plugin.name: plugin}, StrategyStore(strategies_dir))
    model = FakeModel(lambda messages, tools, tool_choice: fake_text(GOOD, 1, 1))
    resp = train(req, model)
    assert resp["usage"]["model_calls"] == len(model.calls) > 0  # before the fix each failed score counted twice
