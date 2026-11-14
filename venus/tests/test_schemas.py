import json

import pytest
from jsonschema import Draft202012Validator

from venus.schemas import load_schema

PAIRS = [
    ("request_training.json", "request"),
    ("request_run.json", "request"),
    ("response_training.json", "response"),
    ("response_run.json", "response"),
]


@pytest.mark.parametrize("name", ["plugin", "strategy", "request", "response"])
def test_schemas_are_valid_json_schemas(name):
    Draft202012Validator.check_schema(load_schema(name))


@pytest.mark.parametrize("example_name, schema_name", PAIRS)
def test_examples_match_schemas(example, example_name, schema_name):
    Draft202012Validator(load_schema(schema_name)).validate(example(example_name))


def test_fixture_manifest_and_strategies_match_schemas(toy_plugin_dir, strategies_dir):
    Draft202012Validator(load_schema("plugin")).validate(json.loads((toy_plugin_dir / "plugin.json").read_text()))
    validator = Draft202012Validator(load_schema("strategy"))
    for name in ("toy-validated", "toy-draft", "other-plugin"):
        validator.validate(json.loads((strategies_dir / f"{name}.json").read_text()))


def test_response_schema_rejects_scores_in_run_mode(example):
    bad = example("response_run.json")
    bad["scores"] = [{"case_id": "x", "total": 1.0, "parts": {}, "reasons": []}]
    assert not Draft202012Validator(load_schema("response")).is_valid(bad)
