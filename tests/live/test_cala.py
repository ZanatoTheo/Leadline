"""Cala, for real: 3 calls the first time, 0 on reruns (the app's disk cache in app/data/cache keeps every success).

The knowledge query is the app's own bulk-pull query (`ingest.build_dataset.QUERIES[0]`), so this test also fills the
cache that the dataset build and the training cases read. Prints the row keys and whether a lead investor is named."""
import json

from conftest import need

from ingest.build_dataset import QUERIES
from ingest.cala_client import CalaClient

LEAD_WORDS = ("lead", "led by", "lead_investor")


def test_cala_shapes_and_lead_question(counter):
    need("CALA_API_KEY")
    cala = CalaClient(http_client=counter.client, timeout=180.0)  # the knowledge query can take over 30 s

    data = cala.knowledge_query(QUERIES[0])
    rows = data.get("results")
    assert isinstance(rows, list), f"knowledge query reply has no results list: {list(data)}"
    keys = sorted({k for r in rows if isinstance(r, dict) for k in r})
    text = json.dumps(rows).lower()
    lead = any(w in text for w in LEAD_WORDS)
    print(f"\nCALA rows={len(rows)} keys={keys}")
    print(f"CALA lead mentioned: {'yes' if lead else 'no'}")

    name = next((r.get(k) for r in rows if isinstance(r, dict) for k in ("company", "company_name", "name")
                 if isinstance(r.get(k), str) and 1 <= len(r.get(k)) <= 100), None) or "Supercell"
    found = cala.entity_search(name, limit=1)
    entities = found.get("entities")
    assert isinstance(entities, list), f"entity search reply has no entities list: {list(found)}"
    print(f"CALA entity search {name!r}: {len(entities)} hit(s)")

    if entities:
        entity = cala.entity(entities[0]["id"])
        assert entity.get("id") and "properties" in entity, f"entity reply keys: {list(entity)}"
        print(f"CALA entity keys={sorted(entity)}")
    print(f"CALA real HTTP calls this run: {counter.count} (0 means all from cache)")
    assert counter.count <= 3
