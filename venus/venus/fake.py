"""Moved to venus.agent.fake (phase 10). This old name stays for existing imports: it is the same module object."""
import sys

from .agent import fake as _module

sys.modules[__name__] = _module
