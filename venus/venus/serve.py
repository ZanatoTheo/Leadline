"""Serving: `Venus.handle(raw) -> response dict` in-process, and `POST /v1/requests` over HTTP (FastAPI).

handle = check_request (mode gate) → training: `train(...)` | run: `run_case(...)` with the validated strategy.
Every outcome, refusals included, is a response that validates against schemas/response.schema.json."""
import asyncio
import json
import os
import time
import uuid
from pathlib import Path

from .envfile import load_env
from .errors import VenusError
from .agent.core import default_model_factory  # noqa: F401 (also re-exported for old imports)
from .plugin import load_plugins
from .request import MODES, VENUS_VERSION, TrainingRequest, check_request
from .runner import run_case
from .strategy import StrategyStore
from .tools import collect_tools
from .training import train

NOT_FOUND = {"plugin_not_found", "strategy_not_found"}
UPSTREAM = {"model_unavailable": 503, "model_bad_reply": 502, "model_bad_request": 502, "output_invalid": 502,
            "all_cases_failed": 502, "budget_exceeded": 503, "model_auth_failed": 500, "model_config_missing": 500,
            "request_timeout": 504, "storage_failed": 500,
            "cala_config_invalid": 500}


def http_status(code: str) -> int:
    if code in NOT_FOUND:
        return 404
    return UPSTREAM.get(code, 400)


def training_base_model(environ=None) -> dict:
    """The model training requests use: VENUS_TRAIN_MODEL, else the provider's default preset (VENUS_TRAIN_PROVIDER,
    e.g. `claude-research` for anthropic), else the `nemotron` preset."""
    from .config import PROVIDERS
    environ = os.environ if environ is None else environ
    provider = environ.get("VENUS_TRAIN_PROVIDER")
    default = (PROVIDERS.get(provider) or {}).get("default_model") if provider else None
    base = {"model": environ.get("VENUS_TRAIN_MODEL") or default or "nemotron"}
    if provider:
        base["provider"] = provider
    return base


class Venus:
    def __init__(self, plugins_dir="plugins", strategies_dir="strategies", runs_dir="runs", model_factory=None,
                 web_tools=None, env: bool = True, train_base_model: dict | None = None, cala_factory=None):
        """`cala_factory()` returns the run-only Cala tools for one run (a new client, so the call cap is per run).
        Default: venus.cala.cala_tools from the environment. Training never calls it."""
        if env:
            load_env()
        plugins_dir = Path(plugins_dir)
        self.plugins = load_plugins(plugins_dir) if plugins_dir.is_dir() else {}
        self.strategies_dir = Path(strategies_dir)
        self.strategies = StrategyStore(self.strategies_dir)
        self.runs_dir = Path(runs_dir) if runs_dir is not None else None
        self.model_factory = model_factory or default_model_factory()
        if web_tools is None:
            from .web import web_tools as make_web_tools
            web_tools = make_web_tools()
        self.web_tools = list(web_tools)
        self.train_base_model = train_base_model or training_base_model()
        if cala_factory is None:
            from .cala import cala_tools
            cala_factory = cala_tools
        self.cala_factory = cala_factory

    def handle(self, raw) -> dict:
        start = time.monotonic()
        try:
            return self._handle(raw, start)
        except (OSError, UnicodeDecodeError) as e:  # unwritable runs/strategies folder, file that is not UTF-8
            return error_response(raw, VenusError("storage_failed", f"{type(e).__name__}: {e}"), start=start)

    def _handle(self, raw, start) -> dict:
        trace_id = uuid.uuid4().hex
        try:
            request = check_request(raw, self.plugins, self.strategies)
        except VenusError as e:
            return error_response(raw, e, trace_id, start)
        plugin = request.plugin
        warnings = []
        if plugin.web_enabled and not self.web_tools:
            warnings.append("web tools off: no Context.dev key (set CONTEXT_DEV_API_KEY)")

        if isinstance(request, TrainingRequest):
            try:
                model = self.model_factory(self.train_base_model)
                resp = train(request, model, web_tools=self.web_tools, strategies_dir=self.strategies_dir,
                             runs_dir=self.runs_dir, base_model=self.train_base_model)
            except VenusError as e:
                return error_response(raw, e, trace_id, start)
            resp["warnings"] = warnings + resp["warnings"]
            return resp

        strategy = request.strategy
        try:
            model = self.model_factory(strategy.base_model)
            run_tools = self.cala_factory() if plugin.cala_enabled else ()
            tools = collect_tools(plugin, request.input, self.web_tools, settings=strategy.plugin_settings,
                                  run_tools=run_tools, mode="run")
            result = run_case(plugin, request.input, strategy.tendencies, model, tools=tools,
                              **strategy.core_settings)  # max_turns / max_web_calls, checked by check_settings
        except VenusError as e:
            return error_response(raw, e, trace_id, start)
        return {"venus_version": VENUS_VERSION, "plugin": plugin.name, "mode": "run", "strategy": strategy.id,
                "status": "ok", "outputs": [{"output": result.output, "sources": result.sources, "status": "ok"}],
                "trace_id": result.trace_id, "usage": result.usage, "warnings": warnings + result.warnings}


def handle_file(path, **venus_options) -> dict:
    """Read one request from a JSON file and return Venus's response (builds a Venus with `venus_options`)."""
    return Venus(**venus_options).handle(json.loads(Path(path).read_text()))


def error_response(raw, error: VenusError, trace_id: str | None = None, start: float | None = None) -> dict:
    resp = {"venus_version": VENUS_VERSION, "status": "error", "outputs": [], "trace_id": trace_id or uuid.uuid4().hex,
            "usage": {"seconds": round(time.monotonic() - start, 3) if start else 0}, "warnings": [],
            "error": error.to_dict()}
    if isinstance(raw, dict):
        if isinstance(raw.get("plugin"), str):
            resp["plugin"] = raw["plugin"]
        if raw.get("mode") in MODES:
            resp["mode"] = raw["mode"]
            if raw["mode"] == "run" and isinstance(raw.get("strategy"), str):
                resp["strategy"] = raw["strategy"]
    return resp


def create_app(venus: Venus, timeout: float = 900.0):
    from fastapi import FastAPI, Request
    from fastapi.concurrency import run_in_threadpool
    from fastapi.responses import JSONResponse

    from . import __version__
    from .cala import cala_configured

    app = FastAPI(title="Venus", version=__version__)

    @app.post("/v1/requests")
    async def post_request(request: Request):
        try:
            raw = json.loads(await request.body())
        except ValueError as e:
            resp = error_response(None, VenusError("request_invalid", f"body is not JSON: {e}"))
            return JSONResponse(resp, status_code=400)
        try:  # model calls block, so they run in a worker thread; the event loop stays free
            resp = await asyncio.wait_for(run_in_threadpool(venus.handle, raw), timeout)
        except asyncio.TimeoutError:
            resp = error_response(raw, VenusError("request_timeout", f"no answer within {timeout:g}s"))
        code = 200 if resp["status"] != "error" else http_status(resp["error"]["code"])
        return JSONResponse(resp, status_code=code)

    @app.get("/v1/health")
    def health():
        return {"ok": True, "version": __version__, "plugins": sorted(venus.plugins), "web": bool(venus.web_tools),
                "cala": cala_configured()}

    return app
