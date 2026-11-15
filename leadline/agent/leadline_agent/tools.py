"""Tools an agent can call. A plugin's `make_tools(input)` returns a list of `Tool` (or dicts with the same fields);
Venus adds its built-in web tools (`web=True`) unless the plugin opts out, and in run mode its run-only tools (Cala)
when the plugin opts in. A `run_only` tool never reaches a training agent."""
import re
from dataclasses import dataclass
from typing import Callable

from .errors import PluginError
from .models import function_tool

NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict
    fn: Callable  # fn(arguments: dict) -> JSON-serialisable result
    web: bool = False
    run_only: bool = False  # never offered in training (e.g. a lookup into the data the cases are scored against)

    def spec(self) -> dict:
        return function_tool(self.name, self.description, self.parameters)


def as_tool(value) -> Tool:
    if isinstance(value, Tool):
        tool = value
    elif isinstance(value, dict) and callable(value.get("fn")):
        tool = Tool(name=value.get("name", ""), description=value.get("description", ""),
                    parameters=value.get("parameters") or {"type": "object", "properties": {}},
                    fn=value["fn"], web=bool(value.get("web", False)),
                    run_only=bool(value.get("run_only", False)))
    else:
        raise PluginError("plugin_tools_failed", f"a tool must be a Tool or a dict with name, description, "
                                                 f"parameters and fn; got {type(value).__name__}")
    if not isinstance(tool.name, str) or not NAME_RE.match(tool.name):
        raise PluginError("plugin_tools_failed", f"bad tool name {tool.name!r}: use letters, digits, _ or -")
    return tool


MODES = ("run", "train")


def collect_tools(plugin, input, web_tools=(), settings: dict | None = None, run_tools=(), mode: str = "run") -> list:
    """The tools an agent gets for this input: the plugin's own (its factory gets the strategy's plugin settings if
    it takes them), plus the web tools unless the plugin says `"web": false`, plus `run_tools` in run mode when the
    plugin says `"cala": true`. In `mode="train"` every `run_only` tool is dropped, whatever its source."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
    tools = [as_tool(t) for t in plugin.tools(input, settings)]
    if plugin.web_enabled:
        tools += [as_tool(t) for t in web_tools]
    if mode == "run" and getattr(plugin, "cala_enabled", False):
        tools += [as_tool(t) for t in run_tools]
    if mode == "train":
        tools = [t for t in tools if not t.run_only]
    return tools
