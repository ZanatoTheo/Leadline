"""The only place that talks to Venus.

VENUS_MODE=mock (default): return a fixture from fixtures/ with "source": "mock".
VENUS_MODE=live: build one `venus.Venus(plugins_dir, strategies_dir)` (from the
sibling repo, overridable with VENUS_DIR / VENUS_PLUGINS_DIR / VENUS_STRATEGIES_DIR)
and call `.handle()` with the agreed envelope:

    {"venus_version": "1", "plugin": "cala-leads", "mode": "run",
     "strategy": "<validated strategy id>", "input": {"dataset": ..., "request": ...}}

and unwrap outputs[0].output. Venus errors are raised as VenusError and mapped
to HTTP by the API layer. Venus internals are never called directly.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
STRATEGY_ID = os.environ.get("VENUS_STRATEGY", "cala-leads-default")
PLUGIN_ID = os.environ.get("VENUS_PLUGIN", "cala-leads")

_venus = None


class VenusError(Exception):
    def __init__(self, code: str, message: str, path: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.path = path

    def as_dict(self) -> dict:
        d = {"code": self.code, "message": self.message}
        if self.path:
            d["path"] = self.path
        return d


def _mode() -> str:
    return os.environ.get("VENUS_MODE", "mock").lower()


def match(dataset: dict, request: dict) -> dict:
    if _mode() == "live":
        return _live(dataset, request)
    return _mock(request)


def _mock(request: dict) -> dict:
    direction = request.get("direction", "startup_to_investors")
    name = "mock_startup_to_investors.json" if direction == "startup_to_investors" else "mock_investor_to_startups.json"
    fixture_path = FIXTURES / name
    if not fixture_path.exists():
        raise VenusError("fixture_missing", f"fixture not found: {name}")
    result = json.loads(fixture_path.read_text())
    result["source"] = "mock"
    result["run_id"] = result.get("run_id") or uuid.uuid4().hex[:12]
    result["generated_at"] = datetime.now(timezone.utc).isoformat()
    result["request"] = request
    return result


def _get_venus():
    """One cached Venus instance. Venus is imported from the sibling repo
    (VENUS_DIR or ../venus) so no packaging step is needed at the event."""
    global _venus
    if _venus is not None:
        return _venus
    import sys

    venus_dir = os.environ.get("VENUS_DIR") or str(REPO_ROOT / "venus")
    try:
        import venus  # type: ignore
    except ImportError:
        if Path(venus_dir, "venus").is_dir():
            sys.path.insert(0, venus_dir)
        try:
            import venus  # type: ignore
        except ImportError:
            raise VenusError(
                "venus_unavailable",
                "VENUS_MODE=live but the venus package is not importable "
                f"(looked in {venus_dir}); set VENUS_MODE=mock or VENUS_DIR",
            )
    plugins_dir = os.environ.get("VENUS_PLUGINS_DIR", str(REPO_ROOT / "venus" / "plugins"))
    strategies_dir = os.environ.get("VENUS_STRATEGIES_DIR", str(REPO_ROOT / "venus" / "strategies"))
    _venus = venus.Venus(plugins_dir=plugins_dir, strategies_dir=strategies_dir, runs_dir=None)
    return _venus


def _live(dataset: dict, request: dict) -> dict:
    v = _get_venus()
    envelope = {
        "venus_version": "1",
        "plugin": PLUGIN_ID,
        "mode": "run",
        "strategy": STRATEGY_ID,
        "input": {"dataset": dataset, "request": request},
    }
    try:
        response = v.handle(envelope)
    except VenusError:
        raise
    except Exception as e:  # noqa: BLE001
        raise VenusError("venus_error", str(e))
    if response.get("error"):
        err = response["error"]
        raise VenusError(err.get("code", "venus_error"), err.get("message", "unknown"), err.get("path"))
    status = response.get("status")
    if status not in ("ok", "partial"):
        raise VenusError("venus_status", f"unexpected Venus status: {status}")
    outputs = response.get("outputs") or []
    if not outputs or outputs[0].get("status") == "error":
        err = (outputs[0].get("error") if outputs else None) or {}
        raise VenusError(err.get("code", "empty_output"), err.get("message", "Venus returned no usable output"))
    result = outputs[0].get("output")
    if not isinstance(result, dict):
        raise VenusError("bad_output", "Venus output[0].output is not an object")
    result["source"] = "live"
    result.setdefault("run_id", response.get("trace_id") or uuid.uuid4().hex[:12])
    result.setdefault("generated_at", datetime.now(timezone.utc).isoformat())
    if response.get("warnings"):
        result.setdefault("warnings", [])
        result["warnings"] = list(result["warnings"]) + list(response["warnings"])
    return result
