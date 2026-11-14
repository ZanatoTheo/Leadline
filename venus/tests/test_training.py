import json

from jsonschema import Draft202012Validator

from venus.errors import ModelError
from venus.fake import FakeModel, fake_text, fake_tool_call
from venus.plugin import load_plugin
from venus.request import check_request
from venus.schemas import load_schema
from venus.strategy import StrategyStore
from venus.tools import Tool
from venus.training import RESEARCH_MARK, train

SRC = "https://a.example/negation"


def request(toy_plugin_dir, strategies_dir, example):
    plugin = load_plugin(toy_plugin_dir)
    return check_request(example("request_training.json"), {plugin.name: plugin}, StrategyStore(strategies_dir))


def answer(output, sources=()):
    return fake_text(json.dumps({"output": output, "sources": list(sources)}), input_tokens=7, output_tokens=3)


def search_tool():
    return Tool("web_search", "Search.", {"type": "object", "properties": {"query": {"type": "string"}}},
                lambda a: {"results": [{"url": SRC, "title": "Negation in sentiment"}]}, web=True)


def script(case_answers, research_ok=True):
    """Research calls get a search then tendencies; case calls get the next label from case_answers."""
    answers = list(case_answers)

    def reply(messages, tools, tool_choice):
        if RESEARCH_MARK in messages[0]["content"]:
            if tool_choice == "required":
                return fake_tool_call("web_search", {"query": "sentiment negation"})
            if not research_ok:
                return fake_text("I could not decide.")
            return answer({"tendencies": [{"text": "Flip the label when a negation precedes a positive word.",
                                           "sources": [SRC]}]}, [SRC])
        if tool_choice == "required":
            return fake_tool_call("web_search", {"query": "label"})
        nxt = answers.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return answer({"label": nxt}, [SRC])
    return reply


def valid_response(resp):
    errors = list(Draft202012Validator(load_schema("response")).iter_errors(resp))
    assert errors == [], [e.message for e in errors]


def test_training_without_web_scores_cases(toy_plugin_dir, strategies_dir, example):
    model = FakeModel(script(["positive", "positive"]))
    resp = train(request(toy_plugin_dir, strategies_dir, example), model)
    valid_response(resp)
    assert resp["status"] == "ok" and resp["mode"] == "training"
    assert [s["total"] for s in resp["scores"]] == [1.0, 0.0]
    assert any("research skipped" in w for w in resp["warnings"])
    assert "draft_strategy" not in resp
    assert resp["usage"]["model_calls"] == 2


def test_research_drafts_tendencies_and_saves_draft(toy_plugin_dir, strategies_dir, example, tmp_path):
    model = FakeModel(script(["positive", "negative"]))
    resp = train(request(toy_plugin_dir, strategies_dir, example), model, web_tools=[search_tool()],
                 strategies_dir=tmp_path / "strategies", base_model={"model": "nemotron"})
    valid_response(resp)
    draft_id = resp["draft_strategy"]
    strategy = StrategyStore(tmp_path / "strategies").get(draft_id)
    assert strategy.status == "draft" and not strategy.is_validated
    assert strategy.base_model == {"model": "nemotron"}
    texts = [t.text for t in strategy.tendencies]
    assert "Treat 'not' before a positive word as negative." in texts
    researched = [t for t in strategy.tendencies if t.sources]
    assert researched and researched[0].sources == (SRC,)
    case_prompt = [c for c in model.calls if RESEARCH_MARK not in c["messages"][0]["content"]][0]
    assert "Flip the label" in case_prompt["messages"][0]["content"]
    assert [s["total"] for s in resp["scores"]] == [1.0, 1.0]
    assert resp["usage"]["web_calls"] >= 1
    assert resp["outputs"][0]["sources"] == [SRC]


def test_failed_research_keeps_going(toy_plugin_dir, strategies_dir, example, tmp_path):
    model = FakeModel(script(["positive", "negative"], research_ok=False))
    resp = train(request(toy_plugin_dir, strategies_dir, example), model, web_tools=[search_tool()],
                 strategies_dir=tmp_path / "s")
    valid_response(resp)
    assert any("research failed" in w for w in resp["warnings"])
    assert "draft_strategy" not in resp and len(resp["scores"]) == 2


def test_one_failed_case_is_partial(toy_plugin_dir, strategies_dir, example):
    model = FakeModel(script(["positive", ModelError("model_unavailable", "down")]))
    resp = train(request(toy_plugin_dir, strategies_dir, example), model)
    valid_response(resp)
    assert resp["status"] == "partial"
    assert resp["outputs"][1]["status"] == "error" and resp["outputs"][1]["error"]["code"] == "model_unavailable"
    assert [s["case_id"] for s in resp["scores"]] == ["c1"]


def test_all_cases_failed_is_error(toy_plugin_dir, strategies_dir, example):
    model = FakeModel(script([ModelError("model_unavailable", "down")] * 2))
    resp = train(request(toy_plugin_dir, strategies_dir, example), model)
    valid_response(resp)
    assert resp["status"] == "error" and resp["error"]["code"] == "all_cases_failed"


def test_records_written(toy_plugin_dir, strategies_dir, example, tmp_path):
    model = FakeModel(script(["positive", "negative"]))
    resp = train(request(toy_plugin_dir, strategies_dir, example), model, runs_dir=tmp_path / "runs")
    lines = (tmp_path / "runs" / resp["trace_id"] / "training.jsonl").read_text().splitlines()
    records = [json.loads(line) for line in lines]
    assert [r["case_id"] for r in records] == ["c1", "c2"]
    assert records[0]["expected"] == {"label": "positive"} and records[0]["score"]["total"] == 1.0


def test_training_caps_each_case(toy_plugin_dir, strategies_dir, example, monkeypatch):
    import venus.training as training
    seen = []
    real = training.run_case

    def spy(*args, **kwargs):
        seen.append({k: kwargs.get(k) for k in ("max_turns", "max_web_calls")})
        return real(*args, **kwargs)
    monkeypatch.setattr(training, "run_case", spy)
    req = request(toy_plugin_dir, strategies_dir, example)
    train(req, FakeModel(script(["positive"] * 10)))
    assert seen and all(s == {"max_turns": 5, "max_web_calls": 6} for s in seen)
    seen.clear()
    train(req, FakeModel(script(["positive"] * 10)), case_limits={"max_web_calls": 2})
    assert seen and all(s == {"max_turns": 5, "max_web_calls": 2} for s in seen)


def test_unknown_case_limit_is_refused(toy_plugin_dir, strategies_dir, example):
    import pytest
    with pytest.raises(ValueError):
        train(request(toy_plugin_dir, strategies_dir, example), FakeModel([]), case_limits={"max_tokens": 9})


def test_research_keeps_its_own_limits_and_turn_warnings_reach_the_response(toy_plugin_dir, strategies_dir, example,
                                                                            monkeypatch):
    import venus.training as training
    seen = []
    real = training.run_case

    def spy(*args, **kwargs):
        seen.append((kwargs.get("max_turns"), kwargs.get("max_web_calls")))
        return real(*args, **kwargs)
    monkeypatch.setattr(training, "run_case", spy)

    def reply(messages, tools, tool_choice):
        if RESEARCH_MARK in messages[0]["content"] or tool_choice == "none":
            return script(["positive"] * 10)(messages, tools, tool_choice)
        return fake_tool_call("web_search", {"query": "more"})  # case calls keep searching until cut off
    resp = train(request(toy_plugin_dir, strategies_dir, example), FakeModel(reply), web_tools=[search_tool()],
                 case_limits={"max_turns": 3})
    assert seen[0] == (6, None)  # research: unchanged
    assert all(s == (3, 6) for s in seen[1:]) and len(seen) > 1
    assert any(w.startswith("case ") and "turn limit (3)" in w for w in resp["warnings"])


def test_bad_case_limit_values_are_refused(toy_plugin_dir, strategies_dir, example):
    import pytest
    with pytest.raises(ValueError):
        train(request(toy_plugin_dir, strategies_dir, example), FakeModel([]), case_limits={"max_turns": 0})
