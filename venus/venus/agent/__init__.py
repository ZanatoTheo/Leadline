"""venus.agent: the standalone run-time part of Venus (plugins + validated strategies, run mode only).

`venus export` copies this package as `leadline_agent`. It imports only the standard library, jsonschema, openai,
httpx and (lazily, for Anthropic models) anthropic; never venus.serve, venus.training or FastAPI.
Contract: shared_context.md Section 4.2."""
from .core import Agent, AgentError

__all__ = ["Agent", "AgentError"]
