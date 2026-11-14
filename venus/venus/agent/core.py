"""Agent: the standalone run-mode entry point (contract: shared_context.md Section 4.2).

    agent = Agent("dist/leadline-agent")            # holds plugins/ and strategies/
    resp = agent.run("leadline-match", input_data, trace_id=tid, on_cala_result=db.cala_hook(trace_id=tid))

`run()` returns serve's run response plus `base_model` (the model that answered) and never raises for a run problem:
failures come back as `status: "error"` with `error.code`. Only validated strategies run; there is no training here.
Runs on verda/nvidia get `max_tokens` room for reasoning, and a failed primary model can fall back once to another
(`VENUS_FALLBACK_PROVIDER` / `VENUS_FALLBACK_MODEL`)."""
import os
import time
import uuid
from pathlib import Path

from .budget import Budget
from .cache import model_cache_from_env
from .config import resolve_model
from .errors import ModelError, PluginError, VenusError
from .models import CachedModel, ModelClient
from .plugin import load_plugins
from .request import VENUS_VERSION, check_request, run_strategy
from .runner import run_case
from .strategy import StrategyStore
from .tools import collect_tools

FALLBACK_CODES = {"model_unavailable", "model_auth_failed", "model_config_missing", "request_timeout"}
DEFAULT_FALLBACK_MODEL = "nvidia/nemotron-3.5-lightning-30b-a3b"
# Fallback model when VENUS_FALLBACK_MODEL is unset: a model id or a config.PRESETS name, per provider.
DEFAULT_FALLBACK_MODELS = {"nvidia": DEFAULT_FALLBACK_MODEL, "anthropic": "claude-research", "verda": "nemotron",
                           "meta": "meta", "gemini": "gemini"}
REASONING_PROVIDERS = {"verda", "nvidia"}
DEFAULT_MAX_TOKENS = 8192
MAX_MAX_TOKENS = 32768  # Nemotron 3.5 Super VL output limit


class AgentError(Exception):
    """Raised only by `Agent.settings()`; `run()` reports the same codes in its response instead."""

    def __init__(self, code: str, message: str, path: str | None = None):
        super().__init__(f"{code}: {message}")
        self.code, self.message, self.path = code, message, path


def default_model_factory(max_model_calls: int = 100, max_seconds: float = 600, environ=None):
    """base_model dict -> model client with a fresh per-request budget. With `VENUS_MODEL_CACHE=1` the client is
    wrapped in a `CachedModel`. The environment is read on each call, so a `.env` loaded later still counts."""
    def make(base_model: dict):
        env = os.environ if environ is None else environ
        spec = resolve_model(base_model, env)
        budget = Budget(max_model_calls=max_model_calls, max_seconds=max_seconds)
        if spec.client == "anthropic":
            try:
                from .anthropic_client import AnthropicClient  # loaded only when an Anthropic model is used
            except ImportError as e:  # e.g. exported without --fallback-provider anthropic: a run error, not a raise
                raise ModelError("model_config_missing", f"the anthropic package is not installed ({e}); "
                                                         "pip install anthropic", "base_model.provider") from None
            client = AnthropicClient(spec, budget=budget, environ=env)
        else:
            client = ModelClient(spec, budget=budget, environ=env)
        cache = model_cache_from_env(env)
        return client if cache is None else CachedModel(client, cache)
    return make


def max_tokens_from(environ) -> int:
    """`VENUS_MAX_TOKENS` for verda/nvidia runs: default 8192, at most 32768; a bad value gives the default."""
    try:
        value = int(environ.get("VENUS_MAX_TOKENS") or DEFAULT_MAX_TOKENS)
    except (TypeError, ValueError):
        return DEFAULT_MAX_TOKENS
    return min(value, MAX_MAX_TOKENS) if value > 0 else DEFAULT_MAX_TOKENS


def fallback_from(environ) -> dict | None:
    provider = (environ.get("VENUS_FALLBACK_PROVIDER") or "").strip().lower()
    if not provider:
        return None
    model = environ.get("VENUS_FALLBACK_MODEL") or DEFAULT_FALLBACK_MODELS.get(provider, "")
    return {"provider": provider, "model": model}  # an unknown provider with no model -> model_config_missing


class Agent:
    def __init__(self, root_dir=None, *, plugins_dir=None, strategies_dir=None, model=None, model_factory=None,
                 web_tools=None, cala=True, on_cala_result=None, fallback_base_model="env", environ=None):
        root = Path(root_dir) if root_dir is not None else None
        self.plugins_dir = Path(plugins_dir) if plugins_dir is not None else (root / "plugins" if root else None)
        self.strategies_dir = (Path(strategies_dir) if strategies_dir is not None
                               else (root / "strategies" if root else None))
        self.environ = os.environ if environ is None else environ
        self.model = model
        self.model_factory = model_factory or default_model_factory(environ=self.environ)
        if web_tools is None:
            from .web import web_tools as make_web_tools
            web_tools = make_web_tools(environ=self.environ)
        self.web_tools = list(web_tools)
        self.cala = bool(cala)
        self.on_cala_result = on_cala_result
        self.fallback = fallback_from(self.environ) if fallback_base_model == "env" else fallback_base_model
        self._plugins = None

    # -- public --------------------------------------------------------------------------------------------------

    def run(self, plugin_id: str, input_data: dict, strategy: str | None = None, *, trace_id: str | None = None,
            on_cala_result=None) -> dict:
        _check_types(plugin_id, input_data, strategy, trace_id)
        start = time.monotonic()
        trace_id = trace_id or uuid.uuid4().hex
        strategy_id = strategy or f"{plugin_id}-default"
        head = {"venus_version": VENUS_VERSION, "plugin": plugin_id, "mode": "run", "strategy": strategy_id}
        warnings = []
        try:
            plugins, strategies = self._load()
            request = check_request({**head, "input": input_data}, plugins, strategies)
            plugin, strat = request.plugin, request.strategy
            if plugin.web_enabled and not self.web_tools:
                warnings.append("web tools off: no Context.dev key (set CONTEXT_DEV_API_KEY)")
            hook = on_cala_result if on_cala_result is not None else self.on_cala_result
            run_tools = self._cala_tools(hook) if self.cala and plugin.cala_enabled else ()
            tools = collect_tools(plugin, request.input, self.web_tools, settings=strat.plugin_settings,
                                  run_tools=run_tools, mode="run")
        except VenusError as e:
            return _error(head, e, trace_id, start, warnings)

        # One Cala client (and its call cap) for the whole run, fallback included: replies already fetched are hits.
        attempts = [strat.base_model]
        if self.model is None and self.fallback:
            attempts.append(self.fallback)
        primary_error = None
        for i, base_model in enumerate(attempts):
            try:
                model, used, max_tokens = self._model_for(base_model)
                limits = dict(strat.core_settings)
                if max_tokens:
                    limits["max_tokens"] = max_tokens
                result = run_case(plugin, request.input, strat.tendencies, model, tools=tools, **limits)
            except VenusError as e:
                if i + 1 < len(attempts) and e.code in FALLBACK_CODES:
                    warnings.append(f"fell back to {attempts[i + 1].get('provider', 'the fallback model')}: {e.code}")
                    primary_error = e
                    continue
                if primary_error is not None:  # the fallback failed too: report the primary's outage, say why
                    warnings.append(f"fallback to {base_model.get('provider', 'the fallback model')} failed: "
                                    f"{e.code}: {e.message}")
                    e = primary_error
                return _error(head, e, trace_id, start, warnings)
            usage = dict(result.usage)
            usage["seconds"] = round(time.monotonic() - start, 3)
            return {**head, "strategy": strat.id, "status": "ok",
                    "outputs": [{"output": result.output, "sources": result.sources, "status": "ok"}],
                    "trace_id": trace_id, "usage": usage, "base_model": used,
                    "warnings": warnings + result.warnings}

    def settings(self, plugin_id: str, strategy: str | None = None) -> dict:
        """The plugin settings (everything but max_turns / max_web_calls) of the strategy `run()` would use."""
        try:
            plugins, strategies = self._load()
            plugin = plugins.get(plugin_id)
            if plugin is None:
                raise PluginError("plugin_not_found", f"no plugin named {plugin_id!r}", path="plugin")
            return dict(run_strategy(plugin, strategies, strategy or f"{plugin_id}-default").plugin_settings)
        except VenusError as e:
            raise AgentError(e.code, e.message, e.path) from None

    # -- internals -----------------------------------------------------------------------------------------------

    def _load(self):
        if self._plugins is None:
            d = self.plugins_dir
            self._plugins = load_plugins(d, runtime_only=True) if d is not None and d.is_dir() else {}
        return self._plugins, StrategyStore(self.strategies_dir or Path("strategies"))

    def _cala_tools(self, hook):
        from .cala import Cala, cala_tools  # one new client per run, so the call cap is per run
        return cala_tools(Cala(environ=self.environ, on_result=hook))

    def _model_for(self, base_model: dict):
        if self.model is not None:
            return self.model, {"provider": "injected", "model": type(self.model).__name__}, None
        spec = resolve_model(base_model, self.environ)
        model = self.model_factory(base_model)
        max_tokens = max_tokens_from(self.environ) if spec.provider in REASONING_PROVIDERS else None
        return model, {"provider": spec.provider, "model": spec.model}, max_tokens


def _check_types(plugin_id, input_data, strategy, trace_id) -> None:
    if not isinstance(plugin_id, str):
        raise TypeError(f"plugin_id must be a str, got {type(plugin_id).__name__}")
    if not isinstance(input_data, dict):
        raise TypeError(f"input_data must be a dict, got {type(input_data).__name__}")
    for name, value in (("strategy", strategy), ("trace_id", trace_id)):
        if value is not None and not isinstance(value, str):
            raise TypeError(f"{name} must be a str or None, got {type(value).__name__}")


def _error(head, error: VenusError, trace_id, start, warnings) -> dict:
    usage = dict(getattr(error, "usage", None) or {})
    usage["seconds"] = round(time.monotonic() - start, 3)
    return {**head, "status": "error", "outputs": [], "trace_id": trace_id, "usage": usage, "warnings": warnings,
            "error": error.to_dict()}
