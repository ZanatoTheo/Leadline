"""Venus: a general-purpose engine that runs behavioral-tendency strategies for any task defined by a plugin.

Every request is either `training` (validated cases with expected outputs) or `run` (one input, a validated
strategy). Start with `Venus(...).handle(request_dict)`, or serve it with `create_app(Venus(...))`.
See README.md for usage and AGENTS.md for how the code is laid out."""
import importlib

# name -> submodule. Loaded on first use, so `import venus.agent` (the exported runtime) never pulls in serve,
# training or FastAPI.
_EXPORTS = {
    "Agent": "agent", "AgentError": "agent",
    "Budget": "budget", "Cala": "cala", "cala_tools": "cala", "ModelSpec": "config", "resolve_model": "config",
    "find_env_file": "envfile", "load_env": "envfile",
    **{n: "errors" for n in ("BudgetExceeded", "CalaError", "InputError", "ModeError", "ModelError", "PluginError",
                             "StrategyError", "VenusError", "WebError")},
    "FakeModel": "fake", "fake_text": "fake", "fake_tool_call": "fake",
    "ModelClient": "models", "ModelReply": "models", "ToolCall": "models", "function_tool": "models",
    "Plugin": "plugin", "Score": "plugin", "load_plugin": "plugin", "load_plugins": "plugin",
    "VENUS_VERSION": "request", "Case": "request", "RunRequest": "request", "TrainingRequest": "request",
    "check_request": "request", "RunResult": "runner", "run_case": "runner", "load_schema": "schemas",
    "Venus": "serve", "error_response": "serve", "handle_file": "serve", "Strategy": "strategy",
    "StrategyStore": "strategy", "Tendency": "tendency", "Tool": "tools", "collect_tools": "tools",
    "train": "training", "ContextDev": "web", "web_tools": "web",
}


def __getattr__(name):
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module 'venus' has no attribute {name!r}")
    value = getattr(importlib.import_module(f".{module}", __name__), name)
    globals()[name] = value
    return value


__version__ = "0.1.0"


def create_app(venus: "Venus", timeout: float = 900.0):
    """The FastAPI app (`POST /v1/requests`, `GET /v1/health`). FastAPI is imported only when this is called."""
    from .serve import create_app as _create_app
    return _create_app(venus, timeout)


__all__ = [
    "Agent", "AgentError", "VENUS_VERSION", "Budget", "BudgetExceeded", "Cala", "CalaError", "Case", "ContextDev", "FakeModel", "InputError", "ModeError",
    "ModelClient", "ModelError", "ModelReply", "ModelSpec", "Plugin", "PluginError", "RunRequest", "RunResult", "Score",
    "Strategy", "StrategyError", "StrategyStore", "Tendency", "Tool", "ToolCall", "TrainingRequest", "Venus",
    "VenusError", "WebError", "cala_tools", "check_request", "collect_tools", "create_app", "error_response", "fake_text",
    "fake_tool_call", "find_env_file", "function_tool", "handle_file", "load_env", "load_plugin", "load_plugins",
    "load_schema", "resolve_model", "run_case", "train", "web_tools",
]
