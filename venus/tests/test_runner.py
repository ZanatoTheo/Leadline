import json

import pytest

from venus.errors import VenusError
from venus.fake import FakeModel, fake_text, fake_tool_call
from venus.models import ModelError
from venus.plugin import load_plugin
from venus.runner import MAX_TENDENCIES, run_case
from venus.tendency import Tendency
from venus.tools import Tool

QUERY = {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}


@pytest.fixture
def plugin(toy_plugin_dir):
    return load_plugin(toy_plugin_dir)


def answer(output, sources=()):
    return fake_text(json.dumps({"output": output, "sources": list(sources)}), input_tokens=10, output_tokens=5)


def web_search_tool(results=None, calls=None):
    def fn(args):
        if calls is not None:
            calls.append(args)
        return {"results": results or [{"title": "A", "url": "https://a.example/x"}]}
    return Tool("web_search", "Search the web.", QUERY, fn, web=True)


def test_plain_answer_without_tools(plugin):
    model = FakeModel([answer({"label": "positive"})])
    result = run_case(plugin, {"text": "great"}, plugin.seed_tendencies, model)
    assert result.output == {"label": "positive"}
    call = model.calls[0]
    assert call["tools"] is None and call["tool_choice"] is None
    system = call["messages"][0]["content"]
    assert plugin.brief in system and "Treat 'not'" in system
    assert '"great"' in call["messages"][1]["content"]
    assert result.usage == {"model_calls": 1, "input_tokens": 10, "output_tokens": 5,
                            "seconds": result.usage["seconds"], "web_calls": 0, "cache_hits": 0}
    assert result.warnings == []


def test_bare_and_fenced_outputs_accepted(plugin):
    bare = run_case(plugin, {"text": "x"}, [], FakeModel([fake_text('{"label": "negative"}')]))
    assert bare.output == {"label": "negative"}
    fenced = run_case(plugin, {"text": "x"}, [],
                      FakeModel([fake_text('Here:\n```json\n{"output": {"label": "positive"}}\n```')]))
    assert fenced.output == {"label": "positive"}


def test_one_repair_then_valid(plugin):
    model = FakeModel([answer({"label": "meh"}), answer({"label": "negative"})])
    result = run_case(plugin, {"text": "x"}, [], model)
    assert result.output == {"label": "negative"}
    assert len(model.calls) == 2
    assert "label" in model.calls[1]["messages"][-1]["content"]


def test_repair_fails(plugin):
    model = FakeModel([fake_text("no json here"), fake_text("still none")])
    with pytest.raises(VenusError) as e:
        run_case(plugin, {"text": "x"}, [], model)
    assert e.value.code == "output_invalid"


def test_failed_model_reply_still_counts_call_and_reported_usage(plugin):
    class FailedReply:
        def chat(self, *args, **kwargs):
            error = ModelError("model_bad_reply", "reply was cut off")
            error.usage = {"input_tokens": 120, "output_tokens": 8192}
            raise error

    with pytest.raises(ModelError) as e:
        run_case(plugin, {"text": "x"}, [], FailedReply())

    assert e.value.usage["model_calls"] == 1
    assert e.value.usage["input_tokens"] == 120
    assert e.value.usage["output_tokens"] == 8192


def test_web_forces_first_search_and_counts_citations(plugin):
    calls = []
    model = FakeModel([fake_tool_call("web_search", {"query": "sentiment"}),
                       answer({"label": "positive"}, ["https://a.example/x"])])
    result = run_case(plugin, {"text": "x"}, [], model, tools=[web_search_tool(calls=calls)])
    assert model.calls[0]["tool_choice"] == "required"
    assert model.calls[1]["tool_choice"] == "auto"
    assert "search the web" in model.calls[0]["messages"][0]["content"].lower()
    assert calls == [{"query": "sentiment"}]
    tool_msg = model.calls[1]["messages"][-1]
    assert tool_msg["role"] == "tool" and "https://a.example/x" in tool_msg["content"]
    assert result.usage["web_calls"] == 1
    assert result.sources == ["https://a.example/x"]
    assert result.warnings == []
    assert [e["type"] for e in result.trace][:2] == ["model", "tool"]


def test_web_without_citation_warns(plugin):
    model = FakeModel([fake_tool_call("web_search", {"query": "q"}), answer({"label": "positive"})])
    result = run_case(plugin, {"text": "x"}, [], model, tools=[web_search_tool()])
    assert any("cite" in w for w in result.warnings)


def test_tool_errors_are_reported_to_the_model(plugin):
    def boom(args):
        raise RuntimeError("site down")
    tool = Tool("web_search", "Search.", QUERY, boom, web=True)
    model = FakeModel([fake_tool_call("web_search", {"query": "q"}), fake_tool_call("nope", {}),
                       answer({"label": "positive"})])
    result = run_case(plugin, {"text": "x"}, [], model, tools=[tool])
    assert "site down" in model.calls[1]["messages"][-1]["content"]
    assert "unknown tool" in model.calls[2]["messages"][-1]["content"]
    assert result.output == {"label": "positive"}


def test_last_turn_forbids_tools(plugin):
    def script(messages, tools, tool_choice):
        if tool_choice == "none":
            return answer({"label": "negative"})
        return fake_tool_call("web_search", {"query": "again"})
    model = FakeModel(script)
    result = run_case(plugin, {"text": "x"}, [], model, tools=[web_search_tool()], max_turns=3)
    assert [c["tool_choice"] for c in model.calls] == ["required", "auto", "none"]
    assert result.output == {"label": "negative"}


def test_plugin_tools_are_offered(plugin):
    tool = Tool("lookup", "Look up a word.", QUERY, lambda args: {"ok": True})
    model = FakeModel([answer({"label": "positive"})])
    run_case(plugin, {"text": "x"}, [], model, tools=[tool])
    assert model.calls[0]["tool_choice"] == "auto"
    assert model.calls[0]["tools"][0]["function"]["name"] == "lookup"


def test_tendencies_capped(plugin):
    many = [Tendency(f"t{i}", f"rule {i}") for i in range(MAX_TENDENCIES + 3)]
    model = FakeModel([answer({"label": "positive"})])
    result = run_case(plugin, {"text": "x"}, many, model)
    assert f"rule {MAX_TENDENCIES + 2}" not in model.calls[0]["messages"][0]["content"]
    assert any("tendencies" in w for w in result.warnings)


def test_duplicate_tool_names_rejected(plugin):
    with pytest.raises(VenusError) as e:
        run_case(plugin, {"text": "x"}, [], FakeModel([]), tools=[web_search_tool(), web_search_tool()])
    assert e.value.code == "tool_name_duplicate"


# --- training caps (phase 4) --------------------------------------------------------------------------------------

def _searches(n, turn):
    from venus.models import ModelReply, ToolCall
    calls = [ToolCall(id=f"c{turn}_{i}", name="web_search", arguments={"query": f"q{turn}{i}"}) for i in range(n)]
    return ModelReply(text=None, tool_calls=calls, finish_reason="tool_calls")


def test_max_web_calls_caps_a_case_asking_for_10_searches(plugin):
    calls = []
    turns = iter(range(100))

    def reply(messages, tools, tool_choice):
        t = next(turns)
        if t < 2 and tool_choice != "none":
            return _searches(5, t)
        return answer({"label": "positive"}, ["https://a.example/x"])
    result = run_case(plugin, {"text": "x"}, [], FakeModel(reply), tools=[web_search_tool(calls=calls)],
                      max_web_calls=6)
    assert len(calls) == 6 and result.usage["web_calls"] == 6
    assert any("web call limit (6)" in w for w in result.warnings)


def test_reaching_the_turn_limit_is_a_warning(plugin):
    def reply(messages, tools, tool_choice):
        if tool_choice == "none":
            return answer({"label": "positive"}, ["https://a.example/x"])
        return fake_tool_call("web_search", {"query": "again"})
    result = run_case(plugin, {"text": "x"}, [], FakeModel(reply), tools=[web_search_tool()], max_turns=3)
    assert any("turn limit (3)" in w for w in result.warnings)


@pytest.mark.parametrize("limits", [{"max_turns": 0}, {"max_turns": -1}, {"max_turns": "5"}, {"max_turns": True},
                                    {"max_web_calls": -1}, {"max_web_calls": "6"}, {"max_web_calls": 1.5}])
def test_bad_limits_are_refused_up_front(plugin, limits):
    model = FakeModel([])
    with pytest.raises(ValueError):
        run_case(plugin, {"text": "x"}, [], model, tools=[web_search_tool()], **limits)
    assert model.calls == []


def test_one_turn_with_web_asks_for_the_answer_without_a_repair(plugin):
    model = FakeModel([answer({"label": "positive"}, ["https://a.example/x"])])
    result = run_case(plugin, {"text": "x"}, [], model, tools=[web_search_tool()], max_turns=1)
    assert [c["tool_choice"] for c in model.calls] == ["none"]
    assert result.usage["model_calls"] == 1
    assert not any("turn limit" in w for w in result.warnings)  # no tool turn was cut short


# --- providers that support only some tool choices (Anthropic Opus/Sonnet 5.5: auto + none; Meta: auto only) ---

def test_auto_only_provider_never_gets_required_and_is_told_to_search(plugin):
    model = FakeModel([fake_tool_call("web_search", {"query": "x"}), answer({"label": "positive"}, ["https://a.example/x"])],
                      tool_choices=("auto", "none"))
    result = run_case(plugin, {"text": "x"}, [], model, tools=[web_search_tool()])
    assert result.output == {"label": "positive"}
    assert [c["tool_choice"] for c in model.calls] == ["auto", "auto"]
    first = model.calls[0]["messages"]
    assert "web_search" in first[-1]["content"] and first[-1]["role"] == "user"
    assert not any("no forced search" in w for w in result.warnings)


def test_auto_only_reminds_once_when_the_first_reply_skips_the_search(plugin):
    model = FakeModel([answer({"label": "positive"}), fake_tool_call("web_search", {"query": "x"}),
                       answer({"label": "negative"}, ["https://a.example/x"])], tool_choices=("auto", "none"))
    result = run_case(plugin, {"text": "x"}, [], model, tools=[web_search_tool()])
    assert result.output == {"label": "negative"}
    second = model.calls[1]["messages"]
    assert second[-2]["role"] == "assistant" and "have not searched" in second[-1]["content"]
    assert len(model.calls) == 3 and result.warnings == []


def test_auto_only_warns_when_the_model_still_does_not_search(plugin):
    model = FakeModel([answer({"label": "positive"}), answer({"label": "positive"})], tool_choices=("auto", "none"))
    result = run_case(plugin, {"text": "x"}, [], model, tools=[web_search_tool()])
    assert result.output == {"label": "positive"} and len(model.calls) == 2
    assert any("no forced search" in w for w in result.warnings)


def test_provider_without_none_gets_no_tools_on_the_last_turn_and_repair(plugin):
    def script(messages, tools, tool_choice):
        if tools is None:
            return answer({"label": "meh"}) if len([m for m in messages if m["role"] == "assistant"]) < 2 \
                else answer({"label": "positive"}, ["https://a.example/x"])
        return fake_tool_call("web_search", {"query": "x"})
    model = FakeModel(script, tool_choices=("auto",))
    result = run_case(plugin, {"text": "x"}, [], model, tools=[web_search_tool()], max_turns=2)
    assert result.output == {"label": "positive"}
    assert [(c["tool_choice"], c["tools"] is None) for c in model.calls] == [("auto", False), (None, True),
                                                                            (None, True)]


def test_raw_reply_blocks_are_kept_in_history(plugin):
    from venus.models import ModelReply, ToolCall
    raw = [{"type": "thinking", "thinking": "", "signature": "s"},
           {"type": "tool_use", "id": "t1", "name": "web_search", "input": {"query": "x"}}]
    first = ModelReply(text=None, tool_calls=[ToolCall("t1", "web_search", {"query": "x"})], raw=raw,
                       finish_reason="tool_calls")
    model = FakeModel([first, answer({"label": "positive"}, ["https://a.example/x"])])
    run_case(plugin, {"text": "x"}, [], model, tools=[web_search_tool()])
    assistant = [m for m in model.calls[1]["messages"] if m["role"] == "assistant"]
    assert assistant[0]["_raw"] == raw


def test_repair_after_a_tool_call_under_none_sends_no_unpaired_tool_call(plugin):
    """A reply that still calls a tool under tool_choice "none" is not run; the repair must not replay that call,
    or the next request carries a tool call with no tool result (Anthropic answers 400)."""
    from venus.models import ModelReply, ToolCall
    raw = [{"type": "thinking", "thinking": "", "signature": "s"}, {"type": "text", "text": "not json"},
           {"type": "tool_use", "id": "t1", "name": "web_search", "input": {"query": "x"}}]
    bad = ModelReply(text="not json", tool_calls=[ToolCall("t1", "web_search", {"query": "x"})], raw=raw,
                     finish_reason="tool_calls")
    model = FakeModel([bad, answer({"label": "positive"}, ["https://a.example/x"])])
    result = run_case(plugin, {"text": "x"}, [], model, tools=[web_search_tool()], max_turns=1)
    assert result.output == {"label": "positive"}
    repair = model.calls[1]["messages"]
    assistant = [m for m in repair if m["role"] == "assistant"]
    assert not assistant[-1].get("tool_calls")
    assert not any(b.get("type") == "tool_use" for b in assistant[-1].get("_raw") or [])
    assert assistant[-1]["content"]
