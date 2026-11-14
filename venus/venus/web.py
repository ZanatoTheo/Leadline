"""Moved to venus.agent.web (phase 10). This old name stays for existing imports: it is the same module object."""
import sys

from .agent import web as _module

sys.modules[__name__] = _module
