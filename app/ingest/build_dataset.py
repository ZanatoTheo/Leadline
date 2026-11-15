"""Build data/dataset.json from Cala.

With CALA_API_KEY set, this queries Cala for recent seed/Series A rounds and
maps the typed rows into the agreed dataset format. Without a key (or on any
Cala error) it writes the built-in sample dataset so the demo always works,
prints a loud WARNING to stderr, and records why in data/dataset.meta.json:
  {"source": "cala" | "sample", "built_at": iso, "reason": text | null,
   "counts": {"companies": n, "investors": n, "rounds": n}}
With --strict it exits 1 instead of falling back and writes nothing.

Cala field notes (from docs.cala.ai, checked 2026-11-13):
- /v1/knowledge/query returns typed JSON rows for a natural-language question.
- Cala has no dedicated "round" entity type and no native lead-investor flag.
  Who led a round only appears, when it appears at all, inside natural-language
  answers or funding strings. We therefore set role from explicit mentions and
  fall back to "unknown" — never guessed.

Run: python -m ingest.build_dataset [--strict]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest.cala_client import CalaClient, load_env  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUT = DATA_DIR / "dataset.json"
META = DATA_DIR / "dataset.meta.json"

SAMPLE_DATASET = {
    "schema_version": "1.0",
    "companies": [
        {
            "id": "c_lumiforge", "name": "Lumiforge", "description": "Solid-state battery manufacturing for EVs.",
            "website": "https://lumiforge.example", "country": "Finland", "founded": 2022,
            "stage": "seed", "sectors": ["cleantech", "manufacturing"],
            "source": {"ref": "cala:c_lumiforge", "url": "https://cala.ai/e/c_lumiforge"},
        },
        {
            "id": "c_nordwave", "name": "Nordwave Health", "description": "Remote patient monitoring for heart failure.",
            "website": "https://nordwave.example", "country": "Sweden", "founded": 2021,
            "stage": "series_a", "sectors": ["healthtech"],
            "source": {"ref": "cala:c_nordwave", "url": "https://cala.ai/e/c_nordwave"},
        },
        {
            "id": "c_kittencode", "name": "Kittencode", "description": "AI coding assistant for enterprise codebases.",
            "website": "https://kittencode.example", "country": "Estonia", "founded": 2023,
            "stage": "seed", "sectors": ["saas", "ai"],
            "source": {"ref": "cala:c_kittencode", "url": "https://cala.ai/e/c_kittencode"},
        },
        {
            "id": "c_polargrid", "name": "Polargrid", "description": "Grid-scale energy storage software.",
            "website": "https://polargrid.example", "country": "Norway", "founded": 2020,
            "stage": "series_a", "sectors": ["cleantech", "saas"],
            "source": {"ref": "cala:c_polargrid", "url": "https://cala.ai/e/c_polargrid"},
        },
        {
            "id": "c_helixden", "name": "Helixden", "description": "CRISPR-based crop resilience platform.",
            "website": "https://helixden.example", "country": "Denmark", "founded": 2022,
            "stage": "seed", "sectors": ["biotech", "agritech"],
            "source": {"ref": "cala:c_helixden", "url": "https://cala.ai/e/c_helixden"},
        },
        {
            "id": "c_quantlane", "name": "Quantlane", "description": "Real-time fraud detection APIs for banks.",
            "website": "https://quantlane.example", "country": "Finland", "founded": 2021,
            "stage": "series_a", "sectors": ["fintech", "ai"],
            "source": {"ref": "cala:c_quantlane", "url": "https://cala.ai/e/c_quantlane"},
        },
    ],
    "investors": [
        {
            "id": "i_nordic_seed", "name": "Nordic Seed Partners", "kind": "vc", "website": "https://nordicseed.example",
            "country": "Finland", "stage_focus": ["seed"], "sector_focus": ["cleantech", "saas", "ai"],
            "check_size": {"min": 500000, "max": 2500000, "currency": "EUR"},
            "source": {"ref": "cala:i_nordic_seed"},
        },
        {
            "id": "i_baltic_ventures", "name": "Baltic Ventures", "kind": "vc", "website": "https://balticventures.example",
            "country": "Estonia", "stage_focus": ["seed", "series_a"], "sector_focus": ["saas", "ai", "fintech"],
            "check_size": {"min": 1000000, "max": 5000000, "currency": "EUR"},
            "source": {"ref": "cala:i_baltic_ventures"},
        },
        {
            "id": "i_helix_capital", "name": "Helix Capital", "kind": "vc", "website": "https://helixcapital.example",
            "country": "Sweden", "stage_focus": ["series_a", "series_b"], "sector_focus": ["healthtech", "biotech"],
            "check_size": {"min": 5000000, "max": 15000000, "currency": "EUR"},
            "source": {"ref": "cala:i_helix_capital"},
        },
        {
            "id": "i_fjord_impact", "name": "Fjord Impact", "kind": "vc", "website": "https://fjordimpact.example",
            "country": "Norway", "stage_focus": ["seed", "series_a"], "sector_focus": ["cleantech", "agritech"],
            "check_size": {"min": 1000000, "max": 6000000, "currency": "EUR"},
            "source": {"ref": "cala:i_fjord_impact"},
        },
        {
            "id": "i_aurora_angels", "name": "Aurora Angels", "kind": "angel_group", "website": "https://auroraangels.example",
            "country": "Finland", "stage_focus": ["pre_seed", "seed"], "sector_focus": ["saas", "ai", "fintech", "healthtech"],
            "check_size": {"min": 50000, "max": 400000, "currency": "EUR"},
            "source": {"ref": "cala:i_aurora_angels"},
        },
        {
            "id": "i_deepblue_growth", "name": "Deepblue Growth", "kind": "growth", "website": "https://deepbluegrowth.example",
            "country": "Denmark", "stage_focus": ["series_b", "growth"], "sector_focus": ["fintech", "saas"],
            "check_size": {"min": 10000000, "max": 40000000, "currency": "EUR"},
            "source": {"ref": "cala:i_deepblue_growth"},
        },
        {
            "id": "i_meadowlane", "name": "Meadowlane Ventures", "kind": "vc", "website": "https://meadowlane.example",
            "country": "Sweden", "stage_focus": ["seed"], "sector_focus": ["biotech", "healthtech"],
            "check_size": {"min": 400000, "max": 2000000, "currency": "EUR"},
            "source": {"ref": "cala:i_meadowlane"},
        },
    ],
    "rounds": [
        {"id": "r_1", "company_id": "c_lumiforge", "date": "2025-09-12", "stage": "seed",
         "amount": {"value": 1800000, "currency": "EUR"},
         "investors": [{"investor_id": "i_nordic_seed", "role": "lead"},
                       {"investor_id": "i_aurora_angels", "role": "participant"}],
         "source": {"ref": "cala:r_1", "url": "https://cala.ai/e/c_lumiforge"}},
        {"id": "r_2", "company_id": "c_kittencode", "date": "2025-11-03", "stage": "seed",
         "amount": {"value": 2200000, "currency": "EUR"},
         "investors": [{"investor_id": "i_baltic_ventures", "role": "lead"},
                       {"investor_id": "i_aurora_angels", "role": "participant"}],
         "source": {"ref": "cala:r_2", "url": "https://cala.ai/e/c_kittencode"}},
        {"id": "r_3", "company_id": "c_nordwave", "date": "2024-06-20", "stage": "series_a",
         "amount": {"value": 9000000, "currency": "EUR"},
         "investors": [{"investor_id": "i_helix_capital", "role": "lead"},
                       {"investor_id": "i_aurora_angels", "role": "participant"}],
         "source": {"ref": "cala:r_3", "url": "https://cala.ai/e/c_nordwave"}},
        {"id": "r_4", "company_id": "c_polargrid", "date": "2026-02-14", "stage": "series_a",
         "amount": {"value": 7500000, "currency": "EUR"},
         "investors": [{"investor_id": "i_fjord_impact", "role": "lead"},
                       {"investor_id": "i_nordic_seed", "role": "participant"}],
         "source": {"ref": "cala:r_4", "url": "https://cala.ai/e/c_polargrid"}},
        {"id": "r_5", "company_id": "c_helixden", "date": "2025-04-08", "stage": "seed",
         "amount": {"value": 1500000, "currency": "EUR"},
         "investors": [{"investor_id": "i_meadowlane", "role": "lead"},
                       {"investor_id": "i_fjord_impact", "role": "unknown"}],
         "source": {"ref": "cala:r_5", "url": "https://cala.ai/e/c_helixden"}},
        {"id": "r_6", "company_id": "c_quantlane", "date": "2025-08-30", "stage": "series_a",
         "amount": {"value": 11000000, "currency": "EUR"},
         "investors": [{"investor_id": "i_baltic_ventures", "role": "lead"},
                       {"investor_id": "i_deepblue_growth", "role": "participant"}],
         "source": {"ref": "cala:r_6", "url": "https://cala.ai/e/c_quantlane"}},
        {"id": "r_7", "company_id": "c_lumiforge", "date": "2024-01-15", "stage": "pre_seed",
         "amount": {"value": 400000, "currency": "EUR"},
         "investors": [{"investor_id": "i_aurora_angels", "role": "unknown"}],
         "source": {"ref": "cala:r_7", "url": "https://cala.ai/e/c_lumiforge"}},
    ],
    "people": [],
}

QUERIES = [
    "European seed and Series A funding rounds in the last 3 years with company name, "
    "sector, country, round date, stage, amount, currency and investors",
]


def _money(value) -> dict | None:
    # Money always carries a currency; without one the amount is unknown (never assume EUR).
    if isinstance(value, dict) and value.get("value") is not None and value.get("currency"):
        return {"value": value["value"], "currency": value["currency"]}
    return None


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


ROUND_KEYS = ("round_id", "date", "round_date", "round_stage", "amount")


def build_from_cala(client: CalaClient) -> dict:
    """Best-effort mapping of Cala query rows into the dataset format.

    Cala rows vary with the question, so every mapping step tolerates missing
    fields (None) instead of guessing.
    """
    companies, investors, rounds = {}, {}, {}
    for q in QUERIES:
        resp = client.knowledge_query(q)
        rows = resp.get("results") or []
        for row in rows:
            if not isinstance(row, dict):
                continue  # one odd row must not throw away the whole Cala run
            name = row.get("company") or row.get("name")
            raw_cid = row.get("company_id") or row.get("id")
            if not name and not raw_cid:
                continue
            cid = str(raw_cid or f"c_{_slug(name)}")
            companies.setdefault(cid, {
                "id": cid, "name": name,
                "description": row.get("description"), "website": row.get("website"),
                "country": row.get("country"), "founded": row.get("founded_year"),
                "stage": row.get("stage"), "sectors": row.get("sectors") or [],
                "source": {"ref": f"cala:{cid}", "url": row.get("url")},
            })
            links = []
            inv_name = row.get("lead_investor") or row.get("investor")
            raw_iid = row.get("investor_id") or row.get("lead_investor_id")
            if inv_name or raw_iid:
                iid = str(raw_iid or f"inv_{_slug(inv_name)}")
                investors.setdefault(iid, {
                    "id": iid, "name": inv_name,
                    "kind": row.get("investor_kind"), "website": None, "country": None,
                    "stage_focus": [], "sector_focus": [], "check_size": None,
                    "source": {"ref": f"cala:{iid}"},
                })
                role = "lead" if row.get("lead_investor_id") or row.get("lead_investor") else "unknown"
                links = [{"investor_id": iid, "role": role}]
            if not links and not any(row.get(k) for k in ROUND_KEYS):
                continue  # a company row with no round facts: do not invent a round
            rid = str(row.get("round_id") or f"r_{len(rounds)}")
            if rid not in rounds:
                rounds[rid] = {
                    "id": rid, "company_id": cid, "date": row.get("date") or row.get("round_date"),
                    "stage": row.get("round_stage") or row.get("stage"),
                    "amount": _money(row.get("amount")),
                    "investors": links,
                    "source": {"ref": f"cala:{rid}", "url": row.get("url")},
                }
    return {
        "schema_version": "1.0",
        "companies": list(companies.values()),
        "investors": list(investors.values()),
        "rounds": list(rounds.values()),
        "people": [],
    }


def _counts(dataset: dict) -> dict:
    return {k: len(dataset.get(k) or []) for k in ("companies", "investors", "rounds")}


def _write(dataset: dict, source: str, reason: str | None) -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(dataset, indent=2, sort_keys=True))
    meta = {
        "source": source,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "reason": reason,
        "counts": _counts(dataset),
    }
    META.write_text(json.dumps(meta, indent=2, sort_keys=True))
    return meta


def _try_cala() -> tuple[dict | None, str | None]:
    """Returns (dataset, None) on success or (None, reason) on any failure."""
    try:
        client = CalaClient()
        if not client.api_key:
            return None, "CALA_API_KEY is not set (root .env or shell)"
        dataset = build_from_cala(client)
    except Exception as e:  # noqa: BLE001 - any Cala problem is a reason to fall back
        return None, f"Cala ingestion failed: {e}"
    if not dataset["rounds"]:
        return None, "Cala returned no rounds for the ingestion queries"
    return dataset, None


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m ingest.build_dataset")
    parser.add_argument("--strict", action="store_true",
                        help="exit 1 instead of falling back to the sample dataset")
    args = parser.parse_args(argv if argv is not None else [])
    load_env()  # shared_context.md 4.2; CalaClient reads the values

    dataset, reason = _try_cala()
    if dataset is not None:
        meta = _write(dataset, "cala", None)
        print(f"wrote {OUT} from Cala ({meta['counts']})")
        return
    if args.strict:
        print(f"ERROR: --strict and Cala ingestion did not work: {reason}. Nothing written.", file=sys.stderr)
        raise SystemExit(1)
    bar = "!" * 72
    print(f"{bar}\nWARNING: using the SAMPLE dataset, NOT Cala data.\nReason: {reason}\n"
          f"Run with --strict to fail instead.\n{bar}", file=sys.stderr)
    _write(SAMPLE_DATASET, "sample", reason)
    print(f"wrote {OUT} (sample dataset) and {META}")


if __name__ == "__main__":
    main(sys.argv[1:])
