"""Whole live path with no keys and no real network:

stub Cala (httpx.MockTransport) -> CalaClient -> build_from_cala -> dataset
-> app adapter in VENUS_MODE=live -> real Venus (minimal `cala-leads` plugin and validated strategy built in a temp
folder) -> stub model server on 127.0.0.1 -> match result.

Run with the Venus environment (it has openai + jsonschema + httpx):
    cd tests/integration && ../../venus/.venv/bin/python -m pytest -q
"""
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "venus"))

from api import venus_adapter  # noqa: E402
from ingest.build_dataset import build_from_cala  # noqa: E402
from ingest.cala_client import CalaClient  # noqa: E402

CALA_ROWS = [{
    "company_id": "c_demo", "company": "Demo Co", "country": "Finland", "round_stage": "seed",
    "date": "2025-05-01", "amount": {"value": 1000000, "currency": "EUR"},
    "lead_investor_id": "i_demo", "lead_investor": "Demo Fund",
}]
MODEL_ANSWER = {"output": {"matches": [{"candidate_id": "i_demo", "score": 0.9}]}, "sources": []}


def cala_handler(seen):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append({"path": request.url.path, "key": request.headers.get("x-api-key"),
                     "auth": request.headers.get("authorization"), "body": json.loads(request.content or b"{}")})
        return httpx.Response(200, json={"results": CALA_ROWS, "entities": []})
    return handler


class StubModel(BaseHTTPRequestHandler):
    calls = []

    def do_POST(self):  # OpenAI-style chat completions
        body = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))))
        StubModel.calls.append({"path": self.path, "auth": self.headers.get("authorization"), "body": body})
        reply = {"id": "x", "object": "chat.completion", "created": 0, "model": "stub",
                 "choices": [{"index": 0, "finish_reason": "stop",
                              "message": {"role": "assistant", "content": json.dumps(MODEL_ANSWER)}}],
                 "usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10}}
        data = json.dumps(reply).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


@pytest.fixture()
def model_server():
    StubModel.calls = []
    server = HTTPServer(("127.0.0.1", 0), StubModel)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/v1"
    server.shutdown()


def write_plugin(folder: Path):
    plugin = folder / "cala-leads"
    plugin.mkdir(parents=True)
    (plugin / "plugin.json").write_text(json.dumps({
        "name": "cala-leads", "version": "1.0.0", "brief": "Rank investors for a startup.", "web": False,
        "input_schema": "input.schema.json", "output_schema": "output.schema.json", "checker": "checker:check",
        "seed_tendencies": [{"id": "t1", "text": "Prefer investors that led similar rounds."}]}))
    (plugin / "input.schema.json").write_text(json.dumps({
        "type": "object", "required": ["dataset", "request"],
        "properties": {"dataset": {"type": "object"}, "request": {"type": "object"}}}))
    (plugin / "output.schema.json").write_text(json.dumps({
        "type": "object", "required": ["matches"], "properties": {"matches": {"type": "array"}}}))
    (plugin / "checker.py").write_text(
        "def check(input, output, expected):\n    return {'total': 1.0, 'parts': {}, 'reasons': []}\n")


def write_strategy(folder: Path, base_url: str):
    folder.mkdir(parents=True)
    (folder / "cala-leads-default.json").write_text(json.dumps({
        "id": "cala-leads-default", "plugin": "cala-leads", "plugin_version": "1.0.0", "status": "validated",
        "base_model": {"model": "stub", "base_url": base_url, "key_env": "STUB_MODEL_KEY"},
        "tendencies": [{"id": "t1", "text": "Prefer investors that led similar rounds."}],
        "created_at": "2026-11-13T22:00:00Z", "notes": "integration test"}))


@pytest.fixture()
def live(tmp_path, monkeypatch, model_server):
    write_plugin(tmp_path / "plugins")
    write_strategy(tmp_path / "strategies", model_server)
    monkeypatch.setenv("VENUS_MODE", "live")
    monkeypatch.setenv("VENUS_PLUGINS_DIR", str(tmp_path / "plugins"))
    monkeypatch.setenv("VENUS_STRATEGIES_DIR", str(tmp_path / "strategies"))
    monkeypatch.setenv("VENUS_DIR", str(ROOT / "venus"))
    monkeypatch.setenv("STUB_MODEL_KEY", "stub-key-not-real")
    for name in ("CONTEXT_DEV_API_KEY", "CONTEXTDEV_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(venus_adapter, "_venus", None)
    yield tmp_path
    monkeypatch.setattr(venus_adapter, "_venus", None)


def test_cala_to_result_end_to_end(live):
    seen = []
    client = CalaClient(api_key="stub-cala-key", base_url="https://cala.stub", cache_dir=live / "cache",
                        http_client=httpx.Client(transport=httpx.MockTransport(cala_handler(seen))))
    dataset = build_from_cala(client)

    # Cala side: the documented call shape was used
    assert seen, "Cala was never called"
    assert seen[0]["path"] == "/v1/knowledge/query"
    assert seen[0]["key"] == "stub-cala-key" and seen[0]["auth"] is None
    assert "input" in seen[0]["body"] and "query" not in seen[0]["body"]
    assert [c["id"] for c in dataset["companies"]] == ["c_demo"]
    assert dataset["rounds"], "no rounds mapped from Cala rows"

    # Venus side: live mode through the adapter
    request = {"direction": "startup_to_investors", "subject_id": "c_demo", "top_k": 3}
    result = venus_adapter.match(dataset, request)
    assert result["source"] == "live"
    assert result["matches"][0]["candidate_id"] == "i_demo"
    assert result["run_id"] and result["generated_at"]

    # Model side: Venus called our stub with its key and the dataset in the prompt
    assert StubModel.calls, "model stub was never called"
    call = StubModel.calls[0]
    assert call["path"].endswith("/chat/completions")
    assert call["auth"] == "Bearer stub-key-not-real"
    assert "c_demo" in json.dumps(call["body"]["messages"])


def test_missing_plugin_maps_to_plugin_not_found(tmp_path, monkeypatch):
    (tmp_path / "plugins").mkdir()
    (tmp_path / "strategies").mkdir()
    monkeypatch.setenv("VENUS_MODE", "live")
    monkeypatch.setenv("VENUS_PLUGINS_DIR", str(tmp_path / "plugins"))
    monkeypatch.setenv("VENUS_STRATEGIES_DIR", str(tmp_path / "strategies"))
    monkeypatch.setenv("VENUS_DIR", str(ROOT / "venus"))
    monkeypatch.setattr(venus_adapter, "_venus", None)
    with pytest.raises(venus_adapter.VenusError) as e:
        venus_adapter.match({"companies": []}, {"direction": "startup_to_investors", "subject_id": "x"})
    assert e.value.code == "plugin_not_found"
    monkeypatch.setattr(venus_adapter, "_venus", None)
