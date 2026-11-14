"""AnthropicClient: Venus's OpenAI-style messages and tools <-> the Anthropic Messages API, through a stubbed HTTP
transport (httpx2, which the anthropic SDK uses). No network."""
import json

import httpx2
import pytest

from venus.anthropic_client import AnthropicClient
from venus.budget import Budget
from venus.config import ModelSpec
from venus.errors import BudgetExceeded, ModelError
from venus.models import function_tool

SPEC = ModelSpec(provider="anthropic", base_url="https://anthropic.test", model="claude-opus-5-5",
                 key_env="ANTHROPIC_API_KEY", client="anthropic", tool_choices=("auto", "none"))
SEARCH = function_tool("web_search", "Search the web.", {
    "type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]})


def message(content, stop="end_turn", usage=None, model="claude-opus-5-5"):
    return {"id": "msg_1", "type": "message", "role": "assistant", "model": model, "content": content,
            "stop_reason": stop, "stop_sequence": None,
            "usage": usage or {"input_tokens": 20, "output_tokens": 7}}


THINK = {"type": "thinking", "thinking": "", "signature": "sig-abc"}


class Server:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append({"body": json.loads(request.content), "headers": dict(request.headers)})
        status, body = self.responses.pop(0)
        return httpx2.Response(status, json=body)


def client(server, budget=None, sleeps=None, environ=None):
    sleeps = [] if sleeps is None else sleeps
    return AnthropicClient(SPEC, api_key="test-key", budget=budget, environ=environ or {},
                           http_client=httpx2.Client(transport=httpx2.MockTransport(server)), sleep=sleeps.append)


def test_text_reply_usage_and_system_apart():
    server = Server((200, message([{"type": "text", "text": "hello"}],
                                  usage={"input_tokens": 20, "output_tokens": 7, "cache_read_input_tokens": 5,
                                         "cache_creation_input_tokens": 3})))
    reply = client(server).chat([{"role": "system", "content": "be brief"}, {"role": "user", "content": "hi"}])
    assert reply.text == "hello" and reply.tool_calls == []
    assert reply.usage == {"input_tokens": 28, "output_tokens": 7}  # cached input counts too
    assert reply.finish_reason == "stop" and reply.model == "claude-opus-5-5"
    body = server.requests[0]["body"]
    assert body["system"] == "be brief"
    assert body["messages"] == [{"role": "user", "content": "hi"}]
    assert body["model"] == "claude-opus-5-5"


def test_request_params_effort_fallback_cache_min_tokens_no_sampling():
    server = Server((200, message([{"type": "text", "text": "ok"}])))
    client(server, environ={"VENUS_CLAUDE_EFFORT": "high"}).chat(
        [{"role": "user", "content": "hi"}], max_tokens=1024, temperature=0, seed=7)
    req = server.requests[0]
    body = req["body"]
    assert body["max_tokens"] >= 16000  # thinking shares max_tokens; 1024 would cut answers off
    assert body["output_config"] == {"effort": "high"}
    assert body["fallbacks"] == "default"
    assert body["cache_control"] == {"type": "ephemeral"}
    assert body["thinking"]["type"] == "adaptive"
    assert "temperature" not in body and "seed" not in body
    assert "server-side-fallback-2026-07-01" in req["headers"].get("anthropic-beta", "")


def test_tools_and_tool_choice_converted():
    server = Server((200, message([{"type": "tool_use", "id": "toolu_1", "name": "web_search",
                                    "input": {"query": "seed funds"}}], stop="tool_use")))
    reply = client(server).chat([{"role": "user", "content": "find"}], tools=[SEARCH], tool_choice="auto")
    body = server.requests[0]["body"]
    assert body["tools"] == [{"name": "web_search", "description": "Search the web.",
                              "input_schema": SEARCH["function"]["parameters"]}]
    assert body["tool_choice"] == {"type": "auto"}
    assert [(c.id, c.name, c.arguments) for c in reply.tool_calls] == [("toolu_1", "web_search", {"query": "seed funds"})]
    assert reply.finish_reason == "tool_calls"


def test_tool_choice_none_and_required_refused():
    server = Server((200, message([{"type": "text", "text": "done"}])))
    client(server).chat([{"role": "user", "content": "x"}], tools=[SEARCH], tool_choice="none")
    assert server.requests[0]["body"]["tool_choice"] == {"type": "none"}
    with pytest.raises(ModelError) as e:
        client(Server()).chat([{"role": "user", "content": "x"}], tools=[SEARCH], tool_choice="required")
    assert e.value.code == "model_bad_request"


def test_history_replay_raw_blocks_and_grouped_tool_results():
    first = Server((200, message([THINK, {"type": "text", "text": "searching"},
                                  {"type": "tool_use", "id": "t1", "name": "web_search", "input": {"query": "a"}},
                                  {"type": "tool_use", "id": "t2", "name": "web_search", "input": {"query": "b"}}],
                                 stop="tool_use")))
    reply = client(first).chat([{"role": "user", "content": "go"}], tools=[SEARCH], tool_choice="auto")
    assert reply.raw[0] == THINK  # thinking block kept exactly
    messages = [{"role": "user", "content": "go"},
                {"role": "assistant", "content": reply.text, "_raw": reply.raw, "tool_calls": [
                    {"id": "t1", "type": "function", "function": {"name": "web_search", "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": "t1", "content": "r1"},
                {"role": "tool", "tool_call_id": "t2", "content": "r2"},
                {"role": "user", "content": "now answer"}]
    second = Server((200, message([{"type": "text", "text": "final"}])))
    client(second).chat(messages, tools=[SEARCH], tool_choice="none")
    sent = second.requests[0]["body"]["messages"]
    assert sent[1] == {"role": "assistant", "content": reply.raw}  # replayed verbatim, thinking first
    assert sent[2] == {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "t1", "content": "r1"},
        {"type": "tool_result", "tool_use_id": "t2", "content": "r2"},
        {"type": "text", "text": "now answer"}]}
    assert len(sent) == 3


def test_assistant_without_raw_is_rebuilt():
    server = Server((200, message([{"type": "text", "text": "ok"}])))
    client(server).chat([
        {"role": "user", "content": "go"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "t1", "type": "function", "function": {"name": "web_search", "arguments": '{"query": "q"}'}}]},
        {"role": "tool", "tool_call_id": "t1", "content": "r"},
        {"role": "assistant", "content": ""},
        {"role": "user", "content": "fix it"}])
    sent = server.requests[0]["body"]["messages"]
    assert sent[1] == {"role": "assistant", "content": [
        {"type": "tool_use", "id": "t1", "name": "web_search", "input": {"query": "q"}}]}
    assert sent[3]["role"] == "assistant" and sent[3]["content"]  # never an empty assistant turn


def test_later_system_message_becomes_user_text():
    server = Server((200, message([{"type": "text", "text": "ok"}])))
    client(server).chat([{"role": "system", "content": "s"}, {"role": "user", "content": "u"},
                         {"role": "system", "content": "reminder"}])
    body = server.requests[0]["body"]
    assert body["system"] == "s"
    assert body["messages"] == [{"role": "user", "content": [{"type": "text", "text": "u"},
                                                             {"type": "text", "text": "reminder"}]}]


def test_fallback_block_kept_and_earlier_thinking_dropped():
    blocks = [THINK, {"type": "fallback", "from": {"model": "claude-opus-5-5"}, "to": {"model": "claude-opus-4-8"}},
              {"type": "text", "text": "answer"}]
    reply = client(Server((200, message(blocks, model="claude-opus-4-8")))).chat([{"role": "user", "content": "x"}])
    assert [b["type"] for b in reply.raw] == ["fallback", "text"]
    assert reply.raw[0]["from"] == {"model": "claude-opus-5-5"}
    assert reply.text == "answer"


def test_refusal_and_max_tokens():
    refused = message([], stop="refusal")
    refused["stop_details"] = {"type": "refusal", "category": "cyber", "explanation": "no"}
    with pytest.raises(ModelError) as e:
        client(Server((200, refused))).chat([{"role": "user", "content": "x"}])
    assert e.value.code == "model_bad_reply" and "cyber" in e.value.message
    cut = client(Server((200, message([{"type": "text", "text": "par"}], stop="max_tokens")))).chat(
        [{"role": "user", "content": "x"}])
    assert cut.finish_reason == "length"


def test_errors_mapped_and_retried():
    with pytest.raises(ModelError) as e:
        client(Server((401, {"type": "error", "error": {"type": "authentication_error", "message": "bad"}}))).chat(
            [{"role": "user", "content": "x"}])
    assert e.value.code == "model_auth_failed"
    with pytest.raises(ModelError) as e:
        client(Server((400, {"type": "error", "error": {"type": "invalid_request_error", "message": "nope"}}))).chat(
            [{"role": "user", "content": "x"}])
    assert e.value.code == "model_bad_request" and "nope" in e.value.message
    sleeps = []
    server = Server((529, {"type": "error", "error": {"type": "overloaded_error", "message": "busy"}}),
                    (200, message([{"type": "text", "text": "ok"}])))
    assert client(server, sleeps=sleeps).chat([{"role": "user", "content": "x"}]).text == "ok"
    assert len(server.requests) == 2 and sleeps == [1]
    busy = {"type": "error", "error": {"type": "overloaded_error", "message": "busy"}}
    with pytest.raises(ModelError) as e:
        client(Server((529, busy), (529, busy), (529, busy))).chat([{"role": "user", "content": "x"}])
    assert e.value.code == "model_unavailable"


def test_budget_checked_and_charged():
    budget = Budget(max_model_calls=1)
    c = client(Server((200, message([{"type": "text", "text": "ok"}]))), budget=budget)
    c.chat([{"role": "user", "content": "x"}])
    assert budget.spent()["input_tokens"] == 20 and budget.spent()["output_tokens"] == 7
    with pytest.raises(BudgetExceeded):
        c.chat([{"role": "user", "content": "x"}])


def test_missing_key_and_tool_choices_exposed():
    with pytest.raises(ModelError) as e:
        AnthropicClient(SPEC, environ={})
    assert e.value.code == "model_config_missing" and "ANTHROPIC_API_KEY" in e.value.message
    assert set(client(Server()).tool_choices) == {"auto", "none"}


def test_other_sdk_errors_become_a_venus_error(monkeypatch):
    """An SDK error that is neither a status nor a connection error (e.g. a reply that fails validation) must come
    out as a ModelError, not escape raw to the HTTP layer as a 500."""
    import anthropic
    c = client(Server())
    resp = httpx2.Response(200, request=httpx2.Request("POST", "https://anthropic.test/v1/messages"))

    def boom(**params):
        raise anthropic.APIResponseValidationError(response=resp, body=None)
    monkeypatch.setattr(c._client.beta.messages, "create", boom)
    with pytest.raises(ModelError) as e:
        c.chat([{"role": "user", "content": "hi"}])
    assert e.value.code == "model_bad_reply"


def test_empty_user_text_and_tool_result_get_a_placeholder():
    from venus.anthropic_client import to_anthropic_messages
    _, msgs = to_anthropic_messages([
        {"role": "user", "content": ""},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "t1", "type": "function", "function": {"name": "web_search", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "t1", "content": ""}])
    assert msgs[0]["content"]
    assert msgs[2]["content"][0]["content"]


def test_cache_tag_names_the_settings_that_change_replies():
    c = client(Server(), environ={"VENUS_CLAUDE_EFFORT": "high"})
    assert c.cache_tag["effort"] == "high" and c.cache_tag["min_tokens"] == 16000
