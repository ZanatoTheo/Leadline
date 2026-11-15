"""build_dataset: reads Cala `results`, writes dataset.meta.json, warns loudly on
fallback, and --strict exits 1. No network: Cala is an httpx.MockTransport."""

import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest import build_dataset as bd  # noqa: E402
from ingest.cala_client import CalaClient  # noqa: E402

ROW = {
    "company_id": "c1", "company": "Acme", "country": "Finland", "stage": "seed",
    "round_id": "r1", "date": "2026-01-02", "amount": {"value": 1000000, "currency": "EUR"},
    "lead_investor_id": "i1", "lead_investor": "Fund One",
}


@pytest.fixture
def paths(tmp_path, monkeypatch):
    monkeypatch.setattr(bd, "DATA_DIR", tmp_path)
    monkeypatch.setattr(bd, "OUT", tmp_path / "dataset.json")
    monkeypatch.setattr(bd, "META", tmp_path / "dataset.meta.json")
    monkeypatch.delenv("CALA_API_KEY", raising=False)
    # A real root .env on key day must not leak into these tests.
    from ingest import cala_client
    monkeypatch.setattr(cala_client, "load_env", lambda: {})
    return tmp_path


def use_cala(monkeypatch, tmp_path, handler, api_key="test-key-not-real"):
    http = httpx.Client(transport=httpx.MockTransport(handler))
    cache = tmp_path / "cache"

    def factory(*a, **kw):
        return CalaClient(api_key=api_key, base_url="https://cala.test", http_client=http, cache_dir=cache)

    monkeypatch.setattr(bd, "CalaClient", factory)


def read_meta(tmp_path):
    return json.loads((tmp_path / "dataset.meta.json").read_text())


def test_build_from_cala_reads_results(tmp_path):
    http = httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"results": [ROW], "entities": None})))
    client = CalaClient(api_key="k", base_url="https://cala.test", http_client=http, cache_dir=tmp_path)
    ds = bd.build_from_cala(client)
    assert [c["name"] for c in ds["companies"]] == ["Acme"]
    assert ds["rounds"][0]["investors"] == [{"investor_id": "i1", "role": "lead"}]


def test_no_key_falls_back_loudly_and_writes_meta(paths, monkeypatch, capsys):
    monkeypatch.setattr(bd, "load_env", lambda: {})
    use_cala(monkeypatch, paths, lambda r: httpx.Response(500), api_key=None)
    bd.main([])
    err = capsys.readouterr().err
    assert "WARNING" in err and "SAMPLE" in err
    meta = read_meta(paths)
    assert meta["source"] == "sample"
    assert "CALA_API_KEY" in meta["reason"]
    assert meta["counts"] == {"companies": 6, "investors": 7, "rounds": 7}
    assert meta["built_at"]
    assert json.loads((paths / "dataset.json").read_text()) == bd.SAMPLE_DATASET


def test_cala_http_error_falls_back_with_reason(paths, monkeypatch):
    use_cala(monkeypatch, paths, lambda r: httpx.Response(401, json={"detail": "nope"}))
    bd.main([])
    meta = read_meta(paths)
    assert meta["source"] == "sample"
    assert "401" in meta["reason"]


def test_cala_empty_results_falls_back(paths, monkeypatch):
    use_cala(monkeypatch, paths, lambda r: httpx.Response(200, json={"results": [], "entities": None}))
    bd.main([])
    meta = read_meta(paths)
    assert meta["source"] == "sample"
    assert "no rounds" in meta["reason"]


def test_cala_success_writes_cala_meta(paths, monkeypatch):
    use_cala(monkeypatch, paths, lambda r: httpx.Response(200, json={"results": [ROW], "entities": None}))
    bd.main([])
    meta = read_meta(paths)
    assert meta["source"] == "cala"
    assert meta["reason"] is None
    assert meta["counts"] == {"companies": 1, "investors": 1, "rounds": 1}
    assert json.loads((paths / "dataset.json").read_text())["rounds"][0]["id"] == "r1"


def test_strict_exits_1_and_writes_nothing(paths, monkeypatch, capsys):
    monkeypatch.setattr(bd, "load_env", lambda: {})
    use_cala(monkeypatch, paths, lambda r: httpx.Response(500), api_key=None)
    with pytest.raises(SystemExit) as e:
        bd.main(["--strict"])
    assert e.value.code == 1
    assert "CALA_API_KEY" in capsys.readouterr().err
    assert not (paths / "dataset.json").exists()


def test_strict_succeeds_with_cala(paths, monkeypatch):
    use_cala(monkeypatch, paths, lambda r: httpx.Response(200, json={"results": [ROW], "entities": None}))
    bd.main(["--strict"])
    assert read_meta(paths)["source"] == "cala"


def test_main_calls_load_env(paths, monkeypatch):
    seen = []
    monkeypatch.setattr(bd, "load_env", lambda: seen.append(True) or {})
    use_cala(monkeypatch, paths, lambda r: httpx.Response(500), api_key=None)
    bd.main([])
    assert seen


# -- partial / odd Cala rows: never guess, never crash -------------------------

def build(tmp_path, rows):
    http = httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"results": rows, "entities": None})))
    client = CalaClient(api_key="k", base_url="https://cala.test", http_client=http, cache_dir=tmp_path)
    return bd.build_from_cala(client)


def test_non_dict_rows_are_skipped(tmp_path):
    ds = build(tmp_path, ["text", None, ROW])
    assert [r["id"] for r in ds["rounds"]] == ["r1"]


def test_row_without_investor_makes_no_nameless_investor(tmp_path):
    row = {"company_id": "c2", "company": "B", "round_id": "r2", "date": "2026-01-01"}
    ds = build(tmp_path, [row])
    assert ds["investors"] == []
    assert ds["rounds"][0]["investors"] == []


def test_missing_currency_gives_null_amount(tmp_path):
    ds = build(tmp_path, [dict(ROW, amount={"value": 5})])
    assert ds["rounds"][0]["amount"] is None


def test_investor_kind_not_guessed(tmp_path):
    ds = build(tmp_path, [ROW])
    assert ds["investors"][0]["kind"] is None
    ds = build(tmp_path / "b", [dict(ROW, investor_kind="angel")])
    assert ds["investors"][0]["kind"] == "angel"


def test_company_only_row_makes_no_round(tmp_path):
    ds = build(tmp_path, [{"company_id": "c3", "company": "C"}])
    assert [c["name"] for c in ds["companies"]] == ["C"]
    assert ds["rounds"] == []


def test_row_without_name_or_id_is_skipped(tmp_path):
    ds = build(tmp_path, [{"country": "Finland"}])
    assert ds["companies"] == [] and ds["rounds"] == []
