"""Load the injected Leadline agent and connect it to Leadline's database."""
from __future__ import annotations

import datetime
import importlib
import importlib.util
import os
import sys
import uuid
from pathlib import Path


DEFAULT_AGENT_DIR = Path(__file__).resolve().parent / "agent"
PREFILTER_PATH = Path(__file__).resolve().parent / "plugins" / "leadline-match" / "prefilter.py"


class AgentLoadError(RuntimeError):
    """The exported leadline_agent package is missing or could not be loaded."""


def load_agent(agent_root=None, **agent_options):
    """Import and instantiate the exported agent from its root directory."""
    environ = agent_options.get("environ")
    environ = os.environ if environ is None else environ
    configured_root = agent_root or environ.get("LEADLINE_AGENT_DIR") or DEFAULT_AGENT_DIR
    root = Path(configured_root).expanduser().resolve()
    if not root.is_dir():
        raise AgentLoadError(f"agent root does not exist: {root}")

    root_text = str(root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    importlib.invalidate_caches()
    try:
        package_spec = importlib.util.find_spec("leadline_agent")
        if package_spec is None or not package_spec.origin:
            raise ModuleNotFoundError("leadline_agent package was not found")
        package_path = Path(package_spec.origin).resolve()
        if root not in package_path.parents:
            raise ImportError(f"leadline_agent resolved outside configured agent root: {package_path}")
        package = importlib.import_module("leadline_agent")
        agent_class = package.Agent
    except (ImportError, AttributeError, OSError) as exc:
        raise AgentLoadError(f"could not load leadline_agent from {root}: {exc}") from exc
    return agent_class(root_dir=root, **agent_options)


def _configured_prefilter(settings):
    """Load a private prefilter module and apply validated strategy settings."""
    spec = importlib.util.spec_from_file_location(f"_leadline_prefilter_{uuid.uuid4().hex}", PREFILTER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load Leadline match prefilter: {PREFILTER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if "rules" in settings:
        enabled = set(settings["rules"])
        module.RULES = tuple(rule for rule in module.RULES if rule[0] in enabled)
    if "min_check_share" in settings:
        module.MIN_CHECK_SHARE = settings["min_check_share"]
    if "max_candidates" in settings:
        module.MAX_CANDIDATES = settings["max_candidates"]
    return module


def _is_agent_error(exc) -> bool:
    """True for the agent's documented `AgentError` (`venus.agent.AgentError` in repo, `leadline_agent.AgentError`
    when exported: two module names for one class), matched by class name so both count. Any other exception, even
    one with a `.code`, is a bug and must stay visible."""
    return any(cls.__name__ == "AgentError" for cls in type(exc).__mro__) and bool(getattr(exc, "code", None))


class AgentBridge:
    """Run validated Leadline plugins through an injected or exported Agent."""

    def __init__(self, db, agent=None, *, agent_root=None, agent_options=None):
        self.db = db
        self.agent = agent if agent is not None else load_agent(agent_root, **(agent_options or {}))

    def run(self, plugin_id, input_data, strategy=None, *, trace_id=None):
        trace = trace_id or uuid.uuid4().hex
        payload = input_data
        if plugin_id == "leadline-match":
            settings, error = self._settings(plugin_id, strategy, trace)
            if error is not None:
                return error
            prefilter = _configured_prefilter(settings)
            try:
                filtered = prefilter.build_input(input_data["subject"], input_data["candidates"],
                                                 input_data["request"])
            except ValueError as exc:  # the subject alone does not fit the input size limit
                return _error_response(plugin_id, strategy, trace, {"code": "input_too_large", "message": str(exc),
                                                                    "path": "input.subject"})
            if filtered["input"] is None:
                return {**_no_match_response(plugin_id, strategy, trace, filtered["rejected"]),
                        "prefilter_cut": filtered["cut"]}
            resp = self.agent.run(plugin_id, filtered["input"], strategy, trace_id=trace,
                                  on_cala_result=self.db.cala_hook(trace_id=trace))
            return {**resp, "prefilter_cut": filtered["cut"]}  # candidates the model never saw (e.g. size cap)

        return self.agent.run(plugin_id, payload, strategy, trace_id=trace,
                              on_cala_result=self.db.cala_hook(trace_id=trace))

    def rank(self, subject, candidates, *, top_k=None, strategy=None, trace_id=None, as_of=None):
        """Rank stored profile records ({key, version, profile, rating}) for one subject record: the trained
        prefilter and `ranking.select_top_n` pick at most `top_k` (default LEADLINE_TOP_N), and only those go to
        leadline-match. With none selected, no model call is made. Returns the run response plus `selected`
        ([[key, fit]]), `prefilter_rejected`, `settings` and `top_n`."""
        from ranking import TOP_N, direction_for, match_profile, select_top_n  # ranking imports this module

        plugin_id, trace = "leadline-match", trace_id or uuid.uuid4().hex
        top_k = max(1, min(int(top_k or TOP_N), 50))  # the input schema allows 1..50
        settings, error = self._settings(plugin_id, strategy, trace)
        if error is not None:
            return error
        subj = match_profile(subject)
        profiles = {p["id"]: p for p in (match_profile(c) for c in candidates)}
        top = select_top_n(subj, list(profiles.values()), settings, n=top_k)
        extra = {"selected": top["selected"], "prefilter_rejected": top["rejected"], "settings": settings,
                 "top_n": top_k, "unseen": []}
        if not top["selected"]:
            return {**_no_match_response(plugin_id, strategy, trace, []), **extra}
        request = {"direction": direction_for(subj), "top_k": top_k,
                   "as_of": as_of or datetime.date.today().isoformat()}
        resp = self.run(plugin_id, {"subject": subj, "candidates": [profiles[k] for k, _ in top["selected"]],
                                    "request": request}, strategy, trace_id=trace)
        unseen = {c["candidate_id"] for c in resp.get("prefilter_cut") or []}
        extra["selected"] = [s for s in top["selected"] if s[0] not in unseen]  # only what the model ranked
        extra["unseen"] = sorted(k for k, _ in top["selected"] if k in unseen)  # offered but cut for size
        return {**resp, **extra}

    def _settings(self, plugin_id, strategy, trace):
        """(settings, None), or (None, an error response) when the agent reports an AgentError."""
        try:
            settings = self.agent.settings(plugin_id, strategy) or {}
        except Exception as exc:
            if not _is_agent_error(exc):
                raise
            error = {"code": exc.code, "message": getattr(exc, "message", str(exc))}
            if getattr(exc, "path", None):
                error["path"] = exc.path
            return None, _error_response(plugin_id, strategy, trace, error)
        if not isinstance(settings, dict):
            raise TypeError("Agent.settings() must return a dictionary")
        return settings, None


def _error_response(plugin_id, strategy, trace, error):
    return {"plugin": plugin_id, "mode": "run", "strategy": strategy or f"{plugin_id}-default", "status": "error",
            "outputs": [], "trace_id": trace, "usage": {}, "warnings": [], "error": error}


def _no_match_response(plugin_id, strategy, trace, rejected):
    """An ok leadline-match response with no matches, made without a model call."""
    return {"plugin": plugin_id, "mode": "run", "strategy": strategy or f"{plugin_id}-default", "status": "ok",
            "outputs": [{"output": {"matches": [], "rejected": rejected, "evidence": [], "warnings": [], "stats": {}},
                         "sources": [], "status": "ok"}], "trace_id": trace,
            "usage": {"model_calls": 0, "input_tokens": 0, "output_tokens": 0, "web_calls": 0, "cache_hits": 0,
                      "seconds": 0}, "warnings": []}
