"""Leadline API: serves search and matching, and the static UI.

Run: uvicorn api.main:app --reload
"""

from __future__ import annotations

import csv
import io
import json
import os
import sys
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from envload import load_env  # noqa: E402

load_env()

from api.venus_adapter import VenusError, match  # noqa: E402

APP_DIR = Path(__file__).resolve().parent.parent
DATASET_PATH = APP_DIR / "data" / "dataset.json"
DATASET_META_PATH = APP_DIR / "data" / "dataset.meta.json"
WEB_DIR = APP_DIR / "web"
RUNS_DIR = APP_DIR / "data" / "runs"

app = FastAPI(title="Leadline", version="0.1.0")

_dataset: dict | None = None
_runs: dict[str, dict] = {}


def load_dataset() -> dict:
    global _dataset
    if _dataset is None:
        if not DATASET_PATH.exists():
            raise RuntimeError("data/dataset.json missing — run: python -m ingest.build_dataset")
        _dataset = json.loads(DATASET_PATH.read_text())
    return _dataset


@app.get("/health")
def health():
    try:
        metadata = json.loads(DATASET_META_PATH.read_text())
        source = metadata.get("source") if isinstance(metadata, dict) else None
    except (OSError, json.JSONDecodeError):
        source = None
    if source not in ("cala", "sample"):
        source = "unknown"
    return {
        "status": "ok",
        "venus_mode": os.environ.get("VENUS_MODE", "mock"),
        "dataset_source": source,
    }


def _search(items: list[dict], q: str, limit: int = 20) -> list[dict]:
    q = q.strip().lower()
    if not q:
        return items[:limit]
    scored = []
    for item in items:
        hay = " ".join(str(item.get(k) or "") for k in ("name", "description", "country", "kind"))
        hay += " " + " ".join(item.get("sectors") or []) + " " + " ".join(item.get("sector_focus") or [])
        if q in hay.lower():
            scored.append(item)
    return scored[:limit]


@app.get("/api/companies")
def companies(q: str = Query("")):
    return _search(load_dataset()["companies"], q)


@app.get("/api/investors")
def investors(q: str = Query("")):
    return _search(load_dataset()["investors"], q)


NOT_FOUND = {"plugin_not_found", "strategy_not_found"}
UPSTREAM = {"model_unavailable": 503, "model_bad_reply": 502, "model_bad_request": 502, "output_invalid": 502,
            "budget_exceeded": 503, "model_auth_failed": 500, "model_config_missing": 500, "request_timeout": 504}


def _venus_http_status(code: str) -> int:
    if code in NOT_FOUND:
        return 404
    if code in UPSTREAM:
        return UPSTREAM[code]
    if code in ("venus_unavailable", "empty_output", "bad_output", "venus_error", "venus_status", "fixture_missing"):
        return 502
    return 400


@app.post("/api/match")
def post_match(request: dict):
    direction = request.get("direction")
    if direction not in ("startup_to_investors", "investor_to_startups"):
        raise HTTPException(status_code=422, detail={
            "code": "bad_direction",
            "message": "direction must be startup_to_investors or investor_to_startups",
            "path": "direction",
        })
    if not request.get("subject_id") and not request.get("subject"):
        raise HTTPException(status_code=422, detail={
            "code": "missing_subject",
            "message": "provide subject_id or an inline subject object",
            "path": "subject_id",
        })
    ds = load_dataset()
    try:
        result = match(ds, request)
    except VenusError as e:
        return JSONResponse(status_code=_venus_http_status(e.code), content={"error": e.as_dict()})
    result.setdefault("request", request)
    for m in result.get("matches", []):
        m["candidate_name"] = _name_of(ds, m.get("candidate_type", "investor"), m.get("candidate_id", ""))
    run_id = result.get("run_id") or uuid.uuid4().hex[:12]
    _runs[run_id] = result
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    (RUNS_DIR / f"{run_id}.json").write_text(json.dumps(result, indent=2))
    return result


def _name_of(ds: dict, kind: str, cid: str) -> str:
    for item in ds["investors" if kind == "investor" else "companies"]:
        if item["id"] == cid:
            return item.get("name") or cid
    return cid


@app.get("/api/export.csv")
def export_csv(run_id: str = Query("")):
    result = _runs.get(run_id)
    if result is None and (RUNS_DIR / f"{run_id}.json").exists():
        result = json.loads((RUNS_DIR / f"{run_id}.json").read_text())
    if result is None:
        raise HTTPException(status_code=404, detail="run_id not found")
    ds = load_dataset()
    subject = (result.get("request") or {}).get("subject_id") or "inline subject"
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["subject", "candidate", "rank", "score", "top_reason"])
    for m in result.get("matches", []):
        top = m.get("reasons", [{}])[0].get("text", "") if m.get("reasons") else ""
        writer.writerow([
            subject,
            _name_of(ds, m.get("candidate_type", "investor"), m.get("candidate_id", "")),
            m.get("rank"),
            m.get("score"),
            top,
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=leadline-{run_id}.csv"},
    )


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(WEB_DIR / "index.html")


app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
