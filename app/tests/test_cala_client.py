"""Cala client matches docs.cala.ai (shared_context.md section 7). No network:
every test passes an httpx.MockTransport and a temp cache dir."""

import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest import cala_client  # noqa: E402
from ingest.cala_client import CalaClient, CalaError  # noqa: E402

FAKE_KEY = "test-key-not-real"


def make_client(tmp_path, handler, api_key=FAKE_KEY):
    calls = []

    def recording(request):
        calls.append(request)
        return handler(request)

    http = httpx.Client(transport=httpx.MockTransport(recording))
    client = CalaClient(api_key=api_key, base_url="https://cala.test", http_client=http, cache_dir=tmp_path)
    return client, calls


def ok(body):
    return lambda request: httpx.Response(200, json=body)


def test_knowledge_query_uses_input_and_api_key_header(tmp_path):
    client, calls = make_client(tmp_path, ok({"results": [{"a": 1}], "entities": None}))
    out = client.knowledge_query("seed rounds in Finland")
    assert out == {"results": [{"a": 1}], "entities": None}
    req = calls[0]
    assert req.method == "POST"
    assert req.url.path == "/v1/knowledge/query"
    assert json.loads(req.content) == {"input": "seed rounds in Finland", "return_entities": True}
    assert req.headers["X-API-KEY"] == FAKE_KEY
    assert "authorization" not in req.headers


def test_entity_search_is_get_with_name_and_limit(tmp_path):
    client, calls = make_client(tmp_path, ok({"entities": []}))
    client.entity_search("Lumiforge", limit=5)
    req = calls[0]
    assert req.method == "GET"
    assert req.url.path == "/v1/entities"
    assert dict(req.url.params) == {"name": "Lumiforge", "limit": "5"}
    assert req.headers["X-API-KEY"] == FAKE_KEY


@pytest.mark.parametrize("name,limit", [("", 10), ("x" * 101, 10), ("ok", 0), ("ok", 101)])
def test_entity_search_rejects_out_of_range(tmp_path, name, limit):
    client, calls = make_client(tmp_path, ok({"entities": []}))
    with pytest.raises(ValueError):
        client.entity_search(name, limit=limit)
    assert calls == []


def test_entity_is_post(tmp_path):
    uid = "123e4567-e89b-12d3-a456-426614174000"
    client, calls = make_client(tmp_path, ok({"id": uid, "name": "X", "entity_type": "Company",
                                              "properties": {}, "relationships": {}}))
    out = client.entity(uid)
    assert out["id"] == uid
    req = calls[0]
    assert req.method == "POST"
    assert req.url.path == f"/v1/entities/{uid}"
    assert req.headers["X-API-KEY"] == FAKE_KEY


def test_entity_passes_optional_body(tmp_path):
    client, calls = make_client(tmp_path, ok({"id": "u"}))
    client.entity("u", properties=["name"], relationships={"investors": {}})
    assert json.loads(calls[0].content) == {"properties": ["name"], "relationships": {"investors": {}}}


def test_second_call_comes_from_cache(tmp_path):
    client, calls = make_client(tmp_path, ok({"results": [], "entities": None}))
    client.knowledge_query("q")
    client.knowledge_query("q")
    assert len(calls) == 1


def test_http_error_is_clear_and_not_cached(tmp_path):
    client, calls = make_client(tmp_path, lambda r: httpx.Response(401, json={"detail": "bad key"}))
    with pytest.raises(CalaError) as e:
        client.knowledge_query("q")
    assert e.value.status == 401
    assert "401" in str(e.value) and "CALA_API_KEY" in str(e.value)
    assert FAKE_KEY not in str(e.value)
    assert list(tmp_path.iterdir()) == []


def test_network_error_is_cala_error(tmp_path):
    def boom(request):
        raise httpx.ConnectError("refused", request=request)

    client, _ = make_client(tmp_path, boom)
    with pytest.raises(CalaError):
        client.knowledge_query("q")


def test_no_key_and_no_cache_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("CALA_API_KEY", raising=False)
    monkeypatch.setattr(cala_client, "load_env", lambda: {})
    client, calls = make_client(tmp_path, ok({}), api_key=None)
    with pytest.raises(CalaError):
        client.knowledge_query("q")
    assert calls == []


def test_init_calls_load_env_and_reads_key_from_it(tmp_path, monkeypatch):
    monkeypatch.delenv("CALA_API_KEY", raising=False)
    monkeypatch.delenv("CALA_BASE_URL", raising=False)
    seen = []

    def fake_load_env():
        seen.append(True)
        return {"CALA_API_KEY": "from-dotenv"}

    monkeypatch.setattr(cala_client, "load_env", fake_load_env)
    client = CalaClient(cache_dir=tmp_path)
    assert seen
    assert client.api_key == "from-dotenv"
    assert client.base_url == "https://api.cala.ai"


def test_shell_env_wins_over_dotenv(tmp_path, monkeypatch):
    monkeypatch.setenv("CALA_API_KEY", "from-shell")
    monkeypatch.setattr(cala_client, "load_env", lambda: {"CALA_API_KEY": "from-dotenv"})
    assert CalaClient(cache_dir=tmp_path).api_key == "from-shell"


# -- T8: ingest/check_live.py (key-day probe) ---------------------------------

def _live_handler(rows):
    def handler(request):
        if request.url.path == "/v1/knowledge/query":
            return httpx.Response(200, json={"results": rows, "entities": None})
        if request.url.path == "/v1/entities" and request.method == "GET":
            return httpx.Response(200, json={"entities": [{"id": "u1", "name": "Wolt", "entity_type": "Company",
                                                           "description": "d"}]})
        if request.url.path == "/v1/entities/u1" and request.method == "POST":
            return httpx.Response(200, json={"id": "u1", "name": "Wolt", "entity_type": "Company",
                                             "properties": {}, "relationships": {}})
        return httpx.Response(404)
    return handler


def test_find_lead_mentions():
    from ingest.check_live import find_lead_mentions
    rows = [{"company": "A", "lead_investor": "Fund X"}, {"company": "B", "lead_investor": None},
            {"company": "C", "note": "Round led by Fund Y"}, {"company": "D"}]
    hits = find_lead_mentions(rows)
    assert [h["row"] for h in hits] == [0, 2]


def test_check_live_reports_rows_and_lead(tmp_path, capsys):
    from ingest.check_live import run
    client, calls = make_client(tmp_path, _live_handler([{"company": "A", "lead_investor": "Fund X"}]))
    code = run(client, n=3)
    out = capsys.readouterr().out
    assert code == 0
    assert "Fund X" in out and "LEAD MENTIONED: yes" in out
    assert {(c.method, c.url.path) for c in calls} == {
        ("POST", "/v1/knowledge/query"), ("GET", "/v1/entities"), ("POST", "/v1/entities/u1")}


def test_check_live_no_lead(tmp_path, capsys):
    from ingest.check_live import run
    client, _ = make_client(tmp_path, _live_handler([{"company": "A"}]))
    assert run(client, n=3) == 0
    assert "LEAD MENTIONED: no" in capsys.readouterr().out


def test_check_live_fails_on_http_error(tmp_path, capsys):
    from ingest.check_live import run
    client, _ = make_client(tmp_path, lambda r: httpx.Response(401))
    assert run(client, n=3) == 1
    assert "401" in capsys.readouterr().out


def test_check_live_main_needs_key(monkeypatch, capsys):
    from ingest import check_live
    monkeypatch.delenv("CALA_API_KEY", raising=False)
    monkeypatch.setattr(cala_client, "load_env", lambda: {})
    assert check_live.main([]) == 2
    assert "CALA_API_KEY" in capsys.readouterr().err
