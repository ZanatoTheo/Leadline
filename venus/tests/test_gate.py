"""The free gate: reject a bad strategy with no model call. Core checks (plugin match, settings, tendencies, cases)
plus cost estimates, then the plugin's own gate.py if it has one."""
import json

import pytest

from venus.fake import FakeModel
from venus.gate import gate
from venus.plugin import load_plugin
from venus.request import Case
from venus.strategy import Strategy

CASES = [Case(id="c1", input={"text": "great"}, expected={"label": "positive"}),
         Case(id="c2", input={"text": "awful"}, expected={"label": "negative"})]


def strategy(**over):
    d = {"id": "s", "plugin": "toy-sentiment", "plugin_version": "1.0.0", "status": "draft",
         "base_model": {"model": "fake-model"}, "tendencies": [{"id": "t1", "text": "Be careful."}],
         "created_at": "2026-11-14T00:00:00Z", **over}
    return Strategy.from_dict(d)


@pytest.fixture
def plugin(toy_plugin_dir):
    return load_plugin(toy_plugin_dir)


def test_good_strategy_passes_with_estimates(plugin):
    r = gate(plugin, strategy(settings={"max_turns": 3, "max_web_calls": 2}), CASES)
    assert r["passed"] is True and r["reasons"] == []
    m = r["metrics"]
    assert m["cases"] == 2 and m["model_calls_per_case_max"] == 3 + 2 and m["web_calls_per_case_max"] == 2
    assert m["input_tokens_per_call_est"] > 0 and m["input_tokens_per_case_est"] >= m["input_tokens_per_call_est"]


def test_gate_makes_no_model_call(plugin, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("the gate must not call a model")
    monkeypatch.setattr(FakeModel, "chat", boom)
    assert gate(plugin, strategy(), CASES)["passed"]


@pytest.mark.parametrize("over,word", [
    ({"plugin": "other"}, "plugin"),
    ({"plugin_version": "9.9.9"}, "version"),
    ({"settings": {"colour": "red"}}, "colour"),
    ({"settings": {"max_turns": 0}}, "max_turns"),
    ({"tendencies": [{"id": f"t{i}", "text": "x"} for i in range(40)]}, "tendencies"),
])
def test_bad_strategy_is_rejected_with_a_reason(plugin, over, word):
    r = gate(plugin, strategy(**over), CASES)
    assert r["passed"] is False and any(word in reason for reason in r["reasons"])


def test_bad_cases_are_named(plugin):
    cases = CASES + [Case(id="bad", input={"txt": 1}, expected={"label": "positive"}),
                     Case(id="worse", input={"text": "ok"}, expected={"label": "maybe"})]
    r = gate(plugin, strategy(), cases)
    assert r["passed"] is False
    assert any("bad" in x for x in r["reasons"]) and any("worse" in x for x in r["reasons"])


def test_no_cases_fails(plugin):
    assert gate(plugin, strategy(), [])["passed"] is False


def test_cases_as_dicts_are_accepted(plugin):
    assert gate(plugin, strategy(), [{"id": c.id, "input": c.input, "expected": c.expected} for c in CASES])["passed"]


def test_cost_caps(plugin):
    r = gate(plugin, strategy(settings={"max_turns": 8}), CASES, max_model_calls_per_case=4)
    assert r["passed"] is False and any("model calls" in x for x in r["reasons"])


def _with_gate(plugin_copy, body, **manifest):
    d = plugin_copy(**manifest)
    (d / "gate.py").write_text(body)
    return load_plugin(d)


def test_plugin_gate_gets_plugin_settings_and_cases(plugin_copy):
    body = ("import json\n"
            "def gate(settings, cases):\n"
            "    ok = settings.get('rules') != ['bad']\n"
            "    return {'passed': ok, 'metrics': {'seen': len(cases), 'settings': json.dumps(settings)},\n"
            "            'reasons': [] if ok else ['case c1: rule bad drops the answer']}\n")
    schema = {"type": "object", "additionalProperties": False, "properties": {"rules": {"type": "array"}}}
    p = _with_gate(plugin_copy, body, settings_schema=schema)
    good = gate(p, strategy(settings={"rules": ["fine"], "max_turns": 2}), CASES)
    assert good["passed"] and good["metrics"]["plugin"]["seen"] == 2
    assert json.loads(good["metrics"]["plugin"]["settings"]) == {"rules": ["fine"]}  # core keys stay with Venus
    bad = gate(p, strategy(settings={"rules": ["bad"]}), CASES)
    assert bad["passed"] is False and "case c1: rule bad drops the answer" in bad["reasons"]


def test_a_failing_plugin_gate_is_a_rejection_not_a_crash(plugin_copy):
    p = _with_gate(plugin_copy, "def gate(settings, cases):\n    raise RuntimeError('oops')\n")
    r = gate(p, strategy(), CASES)
    assert r["passed"] is False and any("oops" in x for x in r["reasons"])


def test_plugin_gate_with_a_bad_reply_is_rejected(plugin_copy):
    p = _with_gate(plugin_copy, "def gate(settings, cases):\n    return {'passed': 'yes'}\n")
    assert gate(p, strategy(), CASES)["passed"] is False


def test_plugin_without_gate_file_has_no_hook(plugin):
    assert plugin.gate_hook is None


# --- phase 7 review fixes ---------------------------------------------------------------------------------------

def test_a_gate_file_that_fails_to_import_does_not_break_the_plugin(plugin_copy):
    d = plugin_copy()
    (d / "gate.py").write_text("import not_a_module_anywhere\n")
    p = load_plugin(d)  # the plugin still loads and serves runs
    r = gate(p, strategy(), CASES)
    assert r["passed"] is False and any("gate" in x for x in r["reasons"])


def test_an_entry_that_is_not_a_case_is_a_reason(plugin):
    r = gate(plugin, strategy(), CASES + ["not a case"])
    assert r["passed"] is False and any("not a case" in x for x in r["reasons"])


def test_the_hook_sees_only_valid_cases(plugin_copy):
    p = _with_gate(plugin_copy, "def gate(settings, cases):\n"
                                "    return {'passed': True, 'metrics': {'ids': [c['id'] for c in cases]}, 'reasons': []}\n")
    bad = Case(id="bad", input={"txt": 1}, expected={"label": "positive"})
    r = gate(p, strategy(), CASES + [bad])
    assert r["metrics"]["plugin"]["ids"] == ["c1", "c2"] and not r["passed"]


def test_hook_reply_with_bad_types_is_rejected(plugin_copy):
    p = _with_gate(plugin_copy, "def gate(settings, cases):\n    return {'passed': True, 'metrics': 3, 'reasons': 'x'}\n")
    assert gate(p, strategy(), CASES)["passed"] is False


def test_token_estimate_counts_web_results(plugin):
    none = gate(plugin, strategy(settings={"max_turns": 3, "max_web_calls": 0}), CASES)["metrics"]
    some = gate(plugin, strategy(settings={"max_turns": 3, "max_web_calls": 4}), CASES)["metrics"]
    assert some["input_tokens_per_case_est"] > none["input_tokens_per_case_est"]
