"""The bundled agent's run-time names, for code that runs one plugin case directly (profiles.py and the tests).

Re-exports what used to come from the venus package. The code is the same: `leadline/agent/leadline_agent` is
exported from `venus.agent`. The agent root is picked at first use, not at import, the way `runtime.load_agent` picks
it (`LEADLINE_AGENT_DIR`, else `leadline/agent`): serve.py reads `--env-file` after its imports, and both must see the
same root.
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import runtime

_NAMES = {
    "Cala": "cala", "cala_tools": "cala",
    "InputError": "errors",
    "FakeModel": "fake", "fake_text": "fake", "fake_tool_call": "fake",
    "load_plugin": "plugin",
    "run_case": "runner",
}
__all__ = sorted(_NAMES)


def agent_root() -> Path:
    return Path(os.environ.get("LEADLINE_AGENT_DIR") or runtime.DEFAULT_AGENT_DIR).expanduser().resolve()


def __getattr__(name):
    if name not in _NAMES:
        raise AttributeError(f"module 'engine' has no attribute {name!r}")
    root = str(agent_root())
    if root not in sys.path:
        sys.path.insert(0, root)
    value = getattr(importlib.import_module(f"leadline_agent.{_NAMES[name]}"), name)
    globals()[name] = value
    return value
