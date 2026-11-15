"""Shared helpers for the Leadline plugin tests: plugin paths and profiles built from the small fixture dataset."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # leadline/*.py (profiles, build_cases) import as top-level modules
PLUGINS = ROOT / "plugins"
FIXTURES = ROOT / "fixtures"
REPO = ROOT.parent


@pytest.fixture
def dataset():
    return json.loads((FIXTURES / "dataset.small.json").read_text())


def company_profile(c: dict) -> dict:
    return {"id": c["id"], "kind": "startup", "name": c["name"], "website": c.get("website"),
            "description": c.get("description"), "country": c.get("country"), "stage": c.get("stage"),
            "sectors": c.get("sectors", []),
            "facts": [{"id": f"d-{c['id']}", "kind": "dataset", "ref": c["source"]["ref"]}]}


def investor_profile(i: dict, lead_share=None, last_lead_date=None) -> dict:
    return {"id": i["id"], "kind": "investor", "name": i["name"], "website": i.get("website"),
            "country": i.get("country"), "stages": i.get("stage_focus", []), "sectors": i.get("sector_focus", []),
            "check_size": i.get("check_size"), "lead_share": lead_share, "last_lead_date": last_lead_date,
            "facts": [{"id": f"d-{i['id']}", "kind": "dataset", "ref": i["source"]["ref"]}]}


@pytest.fixture
def match_input(dataset):
    """Northstar (c_subject) looking for investors as of before its held-out 2025 round (led by i_lead)."""
    subject = company_profile(dataset["companies"][0])
    candidates = [investor_profile(i) for i in dataset["investors"]]
    return {"subject": subject, "candidates": candidates,
            "request": {"direction": "startup_to_investors", "top_k": 2, "as_of": "2025-01-01"}}
