"""Live-mode wiring test: the adapter must build a real venus.Venus and map
its error responses. Uses the actual Venus engine from the sibling repo with
an empty plugins dir, so no network and no models are involved."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
VENUS_REPO = Path(__file__).resolve().parent.parent.parent / "venus"
sys.path.insert(0, str(VENUS_REPO))

pytestmark = pytest.mark.skipif(
    not (VENUS_REPO / "venus" / "__init__.py").exists(), reason="venus repo not present"
)


@pytest.fixture()
def live_client(tmp_path, monkeypatch):
    monkeypatch.setenv("VENUS_MODE", "live")
    monkeypatch.setenv("VENUS_PLUGINS_DIR", str(tmp_path / "plugins"))
    monkeypatch.setenv("VENUS_STRATEGIES_DIR", str(tmp_path / "strategies"))
    (tmp_path / "plugins").mkdir()
    (tmp_path / "strategies").mkdir()
    import api.venus_adapter as adapter
    adapter._venus = None
    from fastapi.testclient import TestClient
    from api.main import app
    client = TestClient(app)
    yield client
    adapter._venus = None


def test_live_mode_maps_plugin_not_found(live_client):
    resp = live_client.post("/api/match", json={
        "direction": "startup_to_investors", "subject_id": "c_lumiforge",
    })
    assert resp.status_code == 404
    err = resp.json()["error"]
    assert err["code"] == "plugin_not_found"
    assert "message" in err
