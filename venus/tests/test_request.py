import copy

import pytest

from venus.errors import InputError, ModeError, PluginError, StrategyError
from venus.plugin import load_plugins
from venus.request import RunRequest, TrainingRequest, check_request
from venus.strategy import StrategyStore


@pytest.fixture
def ctx(toy_plugin_dir, strategies_dir):
    return load_plugins(toy_plugin_dir.parent), StrategyStore(strategies_dir)


def check(raw, ctx):
    plugins, strategies = ctx
    return check_request(raw, plugins, strategies)


def test_valid_training_request(example, ctx):
    req = check(example("request_training.json"), ctx)
    assert isinstance(req, TrainingRequest)
    assert req.plugin.name == "toy-sentiment"
    assert [c.id for c in req.cases] == ["c1", "c2"]
    assert req.cases[1].expected == {"label": "negative"}


def test_valid_run_request(example, ctx):
    req = check(example("request_run.json"), ctx)
    assert isinstance(req, RunRequest)
    assert req.strategy.id == "toy-validated"
    assert req.input == {"text": "This is not good"}


@pytest.mark.parametrize("mode", [None, "predict", 3])
def test_unknown_or_missing_mode(example, ctx, mode):
    raw = example("request_run.json")
    if mode is None:
        del raw["mode"]
    else:
        raw["mode"] = mode
    with pytest.raises(ModeError) as e:
        check(raw, ctx)
    assert e.value.code == "unknown_mode"
    assert e.value.path == "mode"


def test_not_an_object(ctx):
    with pytest.raises(InputError) as e:
        check(["not", "a", "dict"], ctx)
    assert e.value.code == "request_invalid"


def test_unsupported_version(example, ctx):
    raw = example("request_run.json")
    raw["venus_version"] = "2"
    with pytest.raises(InputError) as e:
        check(raw, ctx)
    assert e.value.code == "version_unsupported"


def test_unknown_plugin(example, ctx):
    raw = example("request_run.json")
    raw["plugin"] = "no-such-plugin"
    with pytest.raises(PluginError) as e:
        check(raw, ctx)
    assert e.value.code == "plugin_not_found"
    assert e.value.path == "plugin"


def test_run_with_draft_strategy(example, ctx):
    raw = example("request_run.json")
    raw["strategy"] = "toy-draft"
    with pytest.raises(StrategyError) as e:
        check(raw, ctx)
    assert e.value.code == "strategy_not_validated"


def test_run_with_strategy_for_another_plugin(example, ctx):
    raw = example("request_run.json")
    raw["strategy"] = "other-plugin"
    with pytest.raises(StrategyError) as e:
        check(raw, ctx)
    assert e.value.code == "strategy_plugin_mismatch"


def test_run_without_strategy(example, ctx):
    raw = example("request_run.json")
    del raw["strategy"]
    with pytest.raises(StrategyError) as e:
        check(raw, ctx)
    assert e.value.code == "strategy_missing"


def test_run_with_expected_rejected(example, ctx):
    raw = example("request_run.json")
    raw["expected"] = {"label": "negative"}
    with pytest.raises(InputError) as e:
        check(raw, ctx)
    assert e.value.code == "expected_not_allowed"


def test_run_with_bad_input(example, ctx):
    raw = example("request_run.json")
    raw["input"] = {"text": ""}
    with pytest.raises(InputError) as e:
        check(raw, ctx)
    assert e.value.code == "input_invalid"
    assert e.value.path == "input.text"


def test_training_with_strategy_rejected(example, ctx):
    raw = example("request_training.json")
    raw["strategy"] = "toy-validated"
    with pytest.raises(InputError) as e:
        check(raw, ctx)
    assert e.value.code == "strategy_not_allowed"


@pytest.mark.parametrize("cases, code", [(None, "cases_missing"), ([], "cases_empty")])
def test_training_without_cases(example, ctx, cases, code):
    raw = example("request_training.json")
    if cases is None:
        del raw["cases"]
    else:
        raw["cases"] = cases
    with pytest.raises(InputError) as e:
        check(raw, ctx)
    assert e.value.code == code
    assert e.value.path == "cases"


def test_training_case_without_expected(example, ctx):
    raw = example("request_training.json")
    del raw["cases"][1]["expected"]
    with pytest.raises(InputError) as e:
        check(raw, ctx)
    assert e.value.code == "expected_missing"
    assert e.value.path == "cases[1].expected"


def test_training_invalid_expected(example, ctx):
    raw = example("request_training.json")
    raw["cases"][0]["expected"] = {"label": "meh"}
    with pytest.raises(InputError) as e:
        check(raw, ctx)
    assert e.value.code == "expected_invalid"
    assert e.value.path == "cases[0].expected.label"


def test_training_invalid_input(example, ctx):
    raw = example("request_training.json")
    raw["cases"][1]["input"] = {"words": "x"}
    with pytest.raises(InputError) as e:
        check(raw, ctx)
    assert e.value.code == "input_invalid"
    assert e.value.path.startswith("cases[1].input")


def test_training_duplicate_case_ids(example, ctx):
    raw = example("request_training.json")
    raw["cases"].append(copy.deepcopy(raw["cases"][0]))
    with pytest.raises(InputError) as e:
        check(raw, ctx)
    assert e.value.code == "case_id_duplicate"
    assert e.value.path == "cases[2].id"


def test_unknown_top_level_field(example, ctx):
    raw = example("request_run.json")
    raw["surprise"] = True
    with pytest.raises(InputError) as e:
        check(raw, ctx)
    assert e.value.code == "request_invalid"


def test_errors_serialize(example, ctx):
    raw = example("request_run.json")
    raw["strategy"] = "toy-draft"
    with pytest.raises(StrategyError) as e:
        check(raw, ctx)
    d = e.value.to_dict()
    assert d["code"] == "strategy_not_validated"
    assert "toy-draft" in d["message"]
