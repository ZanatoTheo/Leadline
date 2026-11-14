"""Moved to venus.agent.anthropic_client (phase 10). This old name stays for existing imports: it is the same module object."""
import sys

from .agent import anthropic_client as _module

sys.modules[__name__] = _module
