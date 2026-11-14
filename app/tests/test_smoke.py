"""Smoke tests: the API starts, search works, /api/match returns valid JSON,
and the CSV export works. All against the mock path — no Venus, no network."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DATASET_PATH = Path(__file__).resolve().parent.parent / "data" / "dataset.json"


@pytest.fixture(scope="session", autouse=True)
def dataset():
    if not DATASET_PATH.exists():
        from ingest.build_dataset import main
        main()
    return json.loads(DATASET_PATH.read_text())


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from api.main import app
    return TestClient(app)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_companies_search(client):
    resp = client.get("/api/companies?q=lumi")
    assert resp.status_code == 200
    items = resp.json()
    assert any(i["id"] == "c_lumiforge" for i in items)


def test_investors_search(client):
    resp = client.get("/api/investors?q=nordic")
    assert resp.status_code == 200
    assert any(i["id"] == "i_nordic_seed" for i in resp.json())


def test_match_startup_to_investors(client):
    resp = client.post("/api/match", json={
        "direction": "startup_to_investors", "subject_id": "c_lumiforge",
        "top_k": 10, "as_of": "2026-11-13",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["matches"], "expected at least one match"
    for m in data["matches"]:
        assert 0 <= m["score"] <= 1
        assert "candidate_name" in m
        assert m["reasons"], "each match needs at least one reason"
    assert data["source"] == "mock"


def test_match_investor_to_startups(client):
    resp = client.post("/api/match", json={
        "direction": "investor_to_startups", "subject_id": "i_baltic_ventures",
        "top_k": 10, "as_of": "2026-11-13",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["matches"][0]["candidate_type"] == "company"


def test_match_missing_subject(client):
    resp = client.post("/api/match", json={"direction": "startup_to_investors"})
    assert resp.status_code == 422


def test_export_csv(client):
    resp = client.post("/api/match", json={
        "direction": "startup_to_investors", "subject_id": "c_lumiforge",
    })
    run_id = resp.json()["run_id"]
    resp = client.get(f"/api/export.csv?run_id={run_id}")
    assert resp.status_code == 200
    body = resp.text
    assert body.startswith("subject,candidate,rank,score,top_reason")
    assert "Nordic Seed Partners" in body
