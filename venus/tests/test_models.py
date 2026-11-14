import json

import httpx
import pytest

from venus.budget import Budget
from venus.config import ModelSpec, resolve_model
from venus.errors import BudgetExceeded, ModelError
from venus.fake import FakeModel, fake_text, fake_tool_call
from venus.models import ModelClient, function_tool

SPEC = ModelSpec(provider="verda", base_url="https://verda.test/v1", model="m-1", key_env="VERDA_API_KEY")
SEARCH = function_tool("web_search", "Search the web.", {
    "type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]})


def completion(content=None, tool_calls=None, finish="stop"):
    message = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {"id": "c1", "object": "chat.completion", "created": 0, "model": "m-1",
            "choices": [{"index": 0, "message": message, "finish_reason": finish}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 3, "total_tokens": 14}}


def tool_call_json(name, arguments, call_id="call_1"):
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}}


class Server:
    """A scripted fake endpoint: each request gets the next (status, body) and is recorded."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(json.loads(request.content))
        status, body = self.responses.pop(0)
        return httpx.Response(status, json=body)


def client(server, budget=None, sleeps=None):
    sleeps = [] if sleeps is None else sleeps
    return ModelClient(SPEC, api_key="test-key", budget=budget,
                       http_client=httpx.Client(transport=httpx.MockTransport(server)), sleep=sleeps.append)


def test_text_reply_with_usage():
    reply = client(Server((200, completion("hello")))).chat([{"role": "user", "content": "hi"}])
    assert reply.text == "hello"
    assert reply.tool_calls == []
    assert reply.usage == {"input_tokens": 11, "output_tokens": 3}
    assert reply.model == "m-1"
    assert reply.finish_reason == "stop"


def test_tool_call_parsed():
    server = Server((200, completion(tool_calls=[tool_call_json("web_search", '{"query": "seed investors"}')],
                                     finish="tool_calls")))
    reply = client(server).chat([{"role": "user", "content": "find"}], tools=[SEARCH])
    call = reply.tool_calls[0]
    assert (call.id, call.name, call.arguments, call.parse_error) == ("call_1", "web_search",
                                                                      {"query": "seed investors"}, None)


def test_bad_tool_call_json_is_reported_not_raised():
    server = Server((200, completion(tool_calls=[tool_call_json("web_search", '{"query": ')])))
    call = client(server).chat([{"role": "user", "content": "x"}], tools=[SEARCH]).tool_calls[0]
    assert call.arguments is None
    assert call.parse_error


def test_required_tool_choice_and_tools_sent():
    server = Server((200, completion(tool_calls=[tool_call_json("web_search", '{"query": "q"}')])))
    client(server).chat([{"role": "user", "content": "x"}], tools=[SEARCH], tool_choice="required",
                        temperature=0, seed=7)
    body = server.requests[0]
    assert body["tool_choice"] == "required"
    assert body["tools"][0]["function"]["name"] == "web_search"
    assert body["model"] == "m-1" and body["temperature"] == 0 and body["seed"] == 7


def test_named_tool_choice():
    server = Server((200, completion(tool_calls=[tool_call_json("web_search", '{"query": "q"}')])))
    client(server).chat([{"role": "user", "content": "x"}], tools=[SEARCH], tool_choice={"name": "web_search"})
    assert server.requests[0]["tool_choice"] == {"type": "function", "function": {"name": "web_search"}}


def test_retry_on_429_then_success():
    sleeps = []
    server = Server((429, {"error": {"message": "slow down"}}), (200, completion("ok")))
    assert client(server, sleeps=sleeps).chat([{"role": "user", "content": "x"}]).text == "ok"
    assert len(server.requests) == 2 and len(sleeps) == 1


def test_no_retry_on_401():
    sleeps = []
    server = Server((401, {"error": {"message": "bad key"}}))
    with pytest.raises(ModelError) as e:
        client(server, sleeps=sleeps).chat([{"role": "user", "content": "x"}])
    assert e.value.code == "model_auth_failed"
    assert len(server.requests) == 1 and sleeps == []


def test_bad_request_not_retried():
    server = Server((400, {"error": {"message": "nope"}}))
    with pytest.raises(ModelError) as e:
        client(server).chat([{"role": "user", "content": "x"}])
    assert e.value.code == "model_bad_request"


def test_gives_up_after_repeated_503():
    sleeps = []
    server = Server(*[(503, {"error": {"message": "busy"}})] * 5)
    with pytest.raises(ModelError) as e:
        client(server, sleeps=sleeps).chat([{"role": "user", "content": "x"}])
    assert e.value.code == "model_unavailable"
    assert len(server.requests) == 3 and len(sleeps) == 2  # default max_attempts is 3


def test_budget_charged_and_enforced():
    budget = Budget(max_model_calls=1)
    server = Server((200, completion("one")))
    c = client(server, budget=budget)
    c.chat([{"role": "user", "content": "x"}])
    assert budget.spent()["model_calls"] == 1 and budget.spent()["input_tokens"] == 11
    with pytest.raises(BudgetExceeded) as e:
        c.chat([{"role": "user", "content": "x"}])
    assert e.value.code == "budget_exceeded"
    assert len(server.requests) == 1


def test_resolve_nemotron_preset_uses_verda():
    spec = resolve_model({"model": "nemotron"}, environ={"VERDA_BASE_URL": "https://verda.test/v1"})
    assert spec.provider == "verda" and spec.base_url == "https://verda.test/v1"
    assert spec.key_env == "VERDA_API_KEY" and spec.model


def test_resolve_preset_model_id_from_env():
    spec = resolve_model({"model": "gemma"}, environ={"VERDA_BASE_URL": "https://v/v1", "VENUS_GEMMA_MODEL": "g-x"})
    assert spec.model == "g-x"


def test_resolve_nvidia_fallback():
    spec = resolve_model({"model": "nemotron", "provider": "nvidia"}, environ={})
    assert spec.base_url == "https://integrate.api.nvidia.com/v1" and spec.key_env == "NVIDIA_API_KEY"


def test_missing_verda_base_url():
    with pytest.raises(ModelError) as e:
        resolve_model({"model": "nemotron"}, environ={})
    assert e.value.code == "model_config_missing"
    assert "VERDA_BASE_URL" in e.value.message


def test_missing_api_key():
    with pytest.raises(ModelError) as e:
        ModelClient(SPEC, environ={})
    assert e.value.code == "model_config_missing"


def test_fake_model_scripted_tool_call_then_text():
    fake = FakeModel([fake_tool_call("web_search", {"query": "q"}), fake_text("done")])
    first = fake.chat([{"role": "user", "content": "x"}], tools=[SEARCH], tool_choice="required")
    assert first.tool_calls[0].arguments == {"query": "q"}
    assert fake.chat([{"role": "user", "content": "y"}]).text == "done"
    assert fake.calls[0]["tool_choice"] == "required"
    with pytest.raises(ModelError):
        fake.chat([{"role": "user", "content": "z"}])


# --- rate limiter (phase 3) ---------------------------------------------------------------------------------------

class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.slept = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


def test_limiter_spaces_41_calls_over_a_minute():
    from venus.models import RateLimiter
    clock = FakeClock()
    limiter = RateLimiter(40, clock=clock, sleep=clock.sleep)
    stamps = []
    for _ in range(41):
        limiter.acquire()
        stamps.append(clock.now)
    assert stamps[39] == 0 and stamps[40] >= 60
    assert all(sum(1 for s in stamps if t <= s < t + 60) <= 40 for t in stamps)


def test_limiter_gives_up_past_its_wait_cap():
    from venus.models import RateLimiter
    clock = FakeClock()
    limiter = RateLimiter(1, clock=clock, sleep=clock.sleep, max_wait=10)
    limiter.acquire()
    with pytest.raises(ModelError) as e:
        limiter.acquire()
    assert e.value.code == "model_unavailable" and clock.slept == []


def test_providers_have_rpm():
    from venus.config import PROVIDERS
    assert PROVIDERS["nvidia"]["rpm"] == 40 and PROVIDERS["verda"]["rpm"] is None


def test_nvidia_client_never_sends_more_than_40_a_minute():
    from venus.models import RateLimiter
    clock = FakeClock()
    times = []

    def handler(request):
        times.append(clock.now)
        if sum(1 for t in times if t > clock.now - 60) > 40:
            return httpx.Response(429, json={"error": {"message": "slow down"}})
        return httpx.Response(200, json=completion("ok"))

    spec = ModelSpec(provider="nvidia", base_url="https://nv.test/v1", model="m-1", key_env="NVIDIA_API_KEY")
    c = ModelClient(spec, api_key="k", http_client=httpx.Client(transport=httpx.MockTransport(handler)),
                    sleep=clock.sleep, limiter=RateLimiter(40, clock=clock, sleep=clock.sleep))
    for _ in range(41):
        assert c.chat([{"role": "user", "content": "x"}]).text == "ok"
    assert len(times) == 41 and times[-1] - times[0] >= 60


def test_clients_of_one_provider_share_a_limiter():
    from venus.models import shared_limiter
    nv = ModelSpec(provider="nvidia", base_url="https://nv.test/v1", model="m-1", key_env="NVIDIA_API_KEY")
    a = ModelClient(nv, api_key="k")
    b = ModelClient(nv, api_key="k")
    assert a.limiter is b.limiter is shared_limiter("nvidia", nv.base_url, nv.key_env)
    assert ModelClient(SPEC, api_key="k").limiter is None  # verda has no limit


def test_limiter_wait_respects_the_request_budget():
    from venus.errors import VenusError
    from venus.models import RateLimiter
    clock = FakeClock()
    c = ModelClient(SPEC, api_key="k", budget=Budget(max_seconds=10, clock=clock), sleep=clock.sleep,
                    http_client=httpx.Client(transport=httpx.MockTransport(
                        lambda r: httpx.Response(200, json=completion("ok")))),
                    limiter=RateLimiter(1, clock=clock, sleep=clock.sleep))
    c.chat([{"role": "user", "content": "x"}])
    with pytest.raises(VenusError):
        c.chat([{"role": "user", "content": "x"}])
    assert clock.now < 10  # it did not sleep a full window past the 10 s budget


def test_time_queued_behind_other_threads_counts_toward_the_cap():
    import threading
    from venus.models import RateLimiter
    limiter = RateLimiter(1, window=0.3, max_wait=0.4)
    errors = []

    def go():
        try:
            limiter.acquire()
        except ModelError as e:
            errors.append(e.code)
    threads = [threading.Thread(target=go) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)
    assert errors == ["model_unavailable"]  # the third would have waited ~0.6 s in total


def test_limiters_are_per_endpoint_and_key():
    from venus.models import shared_limiter
    assert shared_limiter("nvidia", "https://a.test/v1", "K1") is shared_limiter("nvidia", "https://a.test/v1", "K1")
    assert shared_limiter("nvidia", "https://a.test/v1", "K1") is not shared_limiter("nvidia", "https://b.test/v1", "K1")
    assert shared_limiter("nvidia", "https://a.test/v1", "K1") is not shared_limiter("nvidia", "https://a.test/v1", "K2")


def test_limiter_keeps_a_safety_margin_past_the_minute():
    from venus.models import RateLimiter
    clock = FakeClock()
    limiter = RateLimiter(1, clock=clock, sleep=clock.sleep)
    limiter.acquire()
    limiter.acquire()
    assert clock.now > 60


def test_limiter_rejects_a_zero_rpm():
    from venus.models import RateLimiter
    with pytest.raises(ValueError):
        RateLimiter(0)


# --- providers added for the Leadline plan: anthropic (working), meta and gemini (off by default) ---

def test_new_providers_resolve_and_presets_carry_their_provider():
    from venus.config import PROVIDERS
    spec = resolve_model({"model": "claude-research"}, {})
    assert (spec.provider, spec.model, spec.client, spec.key_env) == (
        "anthropic", "claude-opus-5-5", "anthropic", "ANTHROPIC_API_KEY")
    assert "required" not in spec.tool_choices and "none" in spec.tool_choices
    fast = resolve_model({"model": "claude-fast"}, {"VENUS_CLAUDE_FAST_MODEL": "claude-haiku-5-5"})
    assert fast.model == "claude-haiku-5-5" and fast.provider == "anthropic"
    meta = resolve_model({"model": "meta"}, {})
    assert (meta.provider, meta.base_url, meta.model, meta.client) == (
        "meta", "https://api.meta.ai/v1", "muse-spark-1.3", "openai")
    assert meta.tool_choices == ("auto",)
    gem = resolve_model({"model": "gemini"}, {})
    assert gem.provider == "gemini" and PROVIDERS["gemini"]["rpm"] == 10
    old = resolve_model({"model": "nemotron", "provider": "nvidia"}, {})
    assert old.client == "openai" and set(old.tool_choices) == {"auto", "required", "none"}
    explicit = resolve_model({"model": "claude-research", "provider": "verda"}, {"VERDA_BASE_URL": "https://v.test"})
    assert explicit.provider == "verda"  # an explicit provider wins over the preset's


def test_training_model_defaults_per_provider():
    from venus.serve import training_base_model
    assert training_base_model({}) == {"model": "nemotron"}
    assert training_base_model({"VENUS_TRAIN_PROVIDER": "anthropic"}) == {"model": "claude-research",
                                                                          "provider": "anthropic"}
    assert training_base_model({"VENUS_TRAIN_PROVIDER": "meta"}) == {"model": "meta", "provider": "meta"}
    assert training_base_model({"VENUS_TRAIN_PROVIDER": "anthropic", "VENUS_TRAIN_MODEL": "claude-fast"})["model"] \
        == "claude-fast"


def test_openai_client_never_sends_internal_fields_and_exposes_tool_choices():
    server = Server((200, completion("ok")))
    c = client(server)
    c.chat([{"role": "user", "content": "hi"},
            {"role": "assistant", "content": "x", "_raw": [{"type": "text", "text": "x"}]},
            {"role": "user", "content": "again"}])
    assert all("_raw" not in m for m in server.requests[0]["messages"])
    assert set(c.tool_choices) == {"auto", "required", "none"}


def test_meta_key_also_read_from_model_api_key():
    spec = resolve_model({"model": "meta"}, {})
    c = ModelClient(spec, environ={"MODEL_API_KEY": "k"},
                    http_client=httpx.Client(transport=httpx.MockTransport(Server((200, completion("ok"))))))
    assert c.chat([{"role": "user", "content": "hi"}]).text == "ok"


def test_model_factory_builds_the_anthropic_client():
    from venus.anthropic_client import AnthropicClient
    from venus.serve import default_model_factory
    made = default_model_factory(environ={"ANTHROPIC_API_KEY": "k"})({"model": "claude-fast"})
    assert isinstance(made, AnthropicClient)


def test_cached_model_keeps_raw_blocks_and_tool_choices(tmp_path):
    from venus.cache import DiskCache
    from venus.models import CachedModel, ModelReply, ToolCall
    raw = [{"type": "thinking", "thinking": "", "signature": "s"},
           {"type": "tool_use", "id": "t1", "name": "web_search", "input": {"q": 1}}]
    inner = FakeModel([ModelReply(text=None, tool_calls=[ToolCall("t1", "web_search", {"q": 1})], raw=raw,
                                  finish_reason="tool_calls")], tool_choices=("auto", "none"))
    cached = CachedModel(inner, DiskCache(tmp_path))
    assert set(cached.tool_choices) == {"auto", "none"}
    msgs = [{"role": "user", "content": "x"}]
    cached.chat(msgs)
    hit = cached.chat(msgs)
    assert hit.cached and hit.raw == raw


def test_cached_model_key_includes_the_inner_cache_tag(tmp_path):
    """Two clients that differ only in a setting the cache key can't see (e.g. Anthropic effort) must not share
    replies."""
    from venus.cache import DiskCache
    from venus.models import CachedModel

    class Tagged(FakeModel):
        def __init__(self, script, tag):
            super().__init__(script)
            self.cache_tag = tag
    cache = DiskCache(tmp_path)
    msgs = [{"role": "user", "content": "hi"}]
    low = Tagged([fake_text("low")], {"effort": "low"})
    assert CachedModel(low, cache, provider="p", model="m").chat(msgs).text == "low"
    high = Tagged([fake_text("high")], {"effort": "high"})
    assert CachedModel(high, cache, provider="p", model="m").chat(msgs).text == "high"
    assert len(high.calls) == 1


def test_call_with_retries_maps_other_sdk_errors():
    from venus.models import call_with_retries

    class Status(Exception):
        pass

    class Conn(Exception):
        pass

    class Base(Exception):
        pass

    class Owner:
        spec = type("S", (), {"provider": "p", "model": "m"})()
        budget = None
        limiter = None
        max_attempts = 3
        sleep = staticmethod(lambda s: None)

    def send():
        raise Base("bad reply shape")
    with pytest.raises(ModelError) as e:
        call_with_retries(Owner(), send, Status, Conn, Base)
    assert e.value.code == "model_bad_reply"


# --- phase 10 (J2): Verda Nemotron 3.5 Super VL ------------------------------------------------------------------

@pytest.mark.parametrize("provider,env,expected", [("verda", "30", 120.0), ("verda", "300", 300.0),
                                                   ("nvidia", "30", 30.0)])
def test_verda_waits_at_least_120_seconds_for_cold_starts(provider, env, expected):
    spec = ModelSpec(provider=provider, base_url="https://x.test/v1", model="m-1", key_env="K")
    c = ModelClient(spec, api_key="k", environ={"VENUS_MODEL_TIMEOUT": env})
    assert c.timeout == expected


def test_reasoning_content_is_dropped_from_the_reply():
    body = completion("hello")
    body["choices"][0]["message"]["reasoning_content"] = "let me think about the secret plan"
    reply = client(Server((200, body))).chat([{"role": "user", "content": "hi"}])
    assert reply.text == "hello" and "secret" not in repr(reply)


@pytest.mark.parametrize("content", [None, "", "   "])
def test_a_reply_cut_off_before_any_answer_is_a_bad_reply(content):
    body = completion(content, finish="length")
    body["choices"][0]["message"]["reasoning_content"] = "thinking " * 50
    with pytest.raises(ModelError) as e:
        client(Server((200, body))).chat([{"role": "user", "content": "hi"}])
    assert e.value.code == "model_bad_reply" and "max_tokens" in e.value.message


def test_a_cut_off_reply_with_some_answer_or_a_tool_call_is_kept():
    assert client(Server((200, completion("{\"partial\":", finish="length")))).chat(
        [{"role": "user", "content": "hi"}]).finish_reason == "length"
    calls = [tool_call_json("web_search", "{\"query\": \"x\"}")]
    assert client(Server((200, completion(None, calls, finish="length")))).chat(
        [{"role": "user", "content": "hi"}]).tool_calls
