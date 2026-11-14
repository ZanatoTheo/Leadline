import json

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from venus.errors import ModelError
from venus.fake import FakeModel, fake_text
from venus.schemas import load_schema
from venus.serve import Venus, create_app


def answer(label):
    return fake_text(json.dumps({"output": {"label": label}, "sources": []}), input_tokens=5, output_tokens=2)


def valid(resp):
    errors = list(Draft202012Validator(load_schema("response")).iter_errors(resp))
    assert errors == [], [e.message for e in errors]
    return resp


@pytest.fixture
def make_venus(toy_plugin_dir, strategies_dir, tmp_path):
    def make(script, web_tools=()):
        seen = []

        def factory(base_model):
            seen.append(base_model)
            if isinstance(script, Exception):
                raise script
            return FakeModel(script)
        v = Venus(plugins_dir=toy_plugin_dir.parent, strategies_dir=strategies_dir, runs_dir=tmp_path / "runs",
                  model_factory=factory, web_tools=list(web_tools), env=False)
        v.seen_models = seen
        return v
    return make


def run_request(**over):
    return {"venus_version": "1", "plugin": "toy-sentiment", "mode": "run", "strategy": "toy-validated",
            "input": {"text": "great"}, **over}


def test_run_uses_validated_strategy(make_venus):
    v = make_venus([answer("positive")])
    resp = valid(v.handle(run_request()))
    assert resp["status"] == "ok" and resp["strategy"] == "toy-validated"
    assert resp["outputs"] == [{"output": {"label": "positive"}, "sources": [], "status": "ok"}]
    assert "scores" not in resp
    assert v.seen_models == [{"model": "fake-model", "key_env": "VERDA_API_KEY"}]
    assert any("web tools off" in w for w in resp["warnings"])


def test_training_through_handle(make_venus, example):
    v = make_venus([answer("positive"), answer("negative")])
    resp = valid(v.handle(example("request_training.json")))
    assert resp["status"] == "ok" and [s["total"] for s in resp["scores"]] == [1.0, 1.0]
    assert v.seen_models[0]["model"]


@pytest.mark.parametrize("raw,code", [
    ({"venus_version": "1", "plugin": "toy-sentiment", "mode": "chat"}, "unknown_mode"),
    (run_request(strategy="toy-draft"), "strategy_not_validated"),
    (run_request(plugin="nope"), "plugin_not_found"),
    ("not an object", "request_invalid"),
])
def test_refused_requests_are_valid_error_responses(make_venus, raw, code):
    resp = valid(make_venus([]).handle(raw))
    assert resp["status"] == "error" and resp["error"]["code"] == code


def test_model_failure_is_error_response(make_venus):
    resp = valid(make_venus(ModelError("model_config_missing", "no key")).handle(run_request()))
    assert resp["error"]["code"] == "model_config_missing" and resp["strategy"] == "toy-validated"


def test_http_run_and_errors(make_venus):
    http = TestClient(create_app(make_venus([answer("negative")])))
    ok = http.post("/v1/requests", json=run_request())
    assert ok.status_code == 200 and ok.json()["outputs"][0]["output"] == {"label": "negative"}

    bad_mode = http.post("/v1/requests", json={"venus_version": "1", "plugin": "toy-sentiment", "mode": "x"})
    assert bad_mode.status_code == 400 and bad_mode.json()["error"]["code"] == "unknown_mode"

    missing = http.post("/v1/requests", json=run_request(plugin="nope"))
    assert missing.status_code == 404

    not_json = http.post("/v1/requests", content=b"{oops", headers={"content-type": "application/json"})
    assert not_json.status_code == 400 and not_json.json()["error"]["code"] == "request_invalid"
    valid(not_json.json())


def test_http_health(make_venus):
    body = TestClient(create_app(make_venus([]))).get("/v1/health").json()
    assert body["ok"] is True and "toy-sentiment" in body["plugins"] and body["web"] is False
