"""Moved to venus.agent.runner (phase 10). This old name stays for existing imports: it is the same module object."""
import sys

from .agent import runner as _module

sys.modules[__name__] = _module
