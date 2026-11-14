"""Key-day probe for Cala. Calls all three endpoints for real (fresh cache, so
nothing old is replayed), prints the first rows, and says whether any row names
a round lead (shared_context.md section 9: "Does Cala ever name a round lead?").

Run (from app/): python -m ingest.check_live [--n 5]
Exit codes: 0 all calls worked, 1 a Cala call failed, 2 no CALA_API_KEY.

Key-day checklist (Julia's part):
  1. Root .env has CALA_API_KEY (T4).
  2. python -m ingest.check_live          -> exit 0, rows printed, "LEAD MENTIONED: yes|no".
  3. python -m ingest.build_dataset --strict -> exit 0, data/dataset.meta.json source "cala".
  4. If the row keys differ from what build_from_cala reads (company, lead_investor,
     round_id, date, amount, ...), send the printed keys to Julia to fix the mapping.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest.build_dataset import QUERIES  # noqa: E402
from ingest.cala_client import CalaClient, CalaError  # noqa: E402

LEAD_TEXT = re.compile(r"\b(led by|lead investor|lead[s]? the round|co-led)\b", re.IGNORECASE)
PROBE_NAME = "Wolt"


def find_lead_mentions(rows: list) -> list[dict]:
    """Rows with a non-empty field whose key contains "lead", or text like "led by"."""
    hits = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        for key, value in row.items():
            if value in (None, "", [], {}):
                continue
            if "lead" in str(key).lower() or (isinstance(value, str) and LEAD_TEXT.search(value)):
                hits.append({"row": i, "key": key, "value": value})
                break
    return hits


def _short(obj, limit: int = 400) -> str:
    text = json.dumps(obj, ensure_ascii=False, sort_keys=True)
    return text if len(text) <= limit else text[:limit] + " ..."


def run(client: CalaClient, n: int = 5) -> int:
    try:
        all_rows = []
        for q in QUERIES:
            resp = client.knowledge_query(q)
            rows = resp.get("results") or []
            ents = resp.get("entities") or []
            all_rows.extend(rows)
            print(f"knowledge_query: {len(rows)} rows, {len(ents)} entities")
            keys = sorted({k for r in rows if isinstance(r, dict) for k in r})
            print(f"  row keys: {keys}")
            for row in rows[:n]:
                print(f"  {_short(row)}")
        hits = find_lead_mentions(all_rows)
        print(f"LEAD MENTIONED: {'yes' if hits else 'no'} ({len(hits)} of {len(all_rows)} rows)")
        for h in hits[:n]:
            print(f"  row {h['row']}: {h['key']} = {_short(h['value'], 200)}")

        found = client.entity_search(PROBE_NAME, limit=3).get("entities") or []
        print(f"entity_search({PROBE_NAME!r}): {len(found)} entities")
        for e in found:
            print(f"  {_short(e, 200)}")
        if found:
            ent = client.entity(found[0]["id"])
            print(f"entity({found[0]['id']}): keys {sorted(ent)}")
    except CalaError as e:
        print(f"FAILED: {e}")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ingest.check_live")
    parser.add_argument("--n", type=int, default=5, help="rows to print per query")
    args = parser.parse_args(argv if argv is not None else [])
    with tempfile.TemporaryDirectory() as cache:
        client = CalaClient(cache_dir=cache)
        if not client.api_key:
            print("CALA_API_KEY is not set (root .env or shell). Nothing to check.", file=sys.stderr)
            return 2
        return run(client, n=args.n)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
