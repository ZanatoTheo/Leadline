"""Real-call tests: they spend real credits, so every test skips unless VENUS_LIVE=1 and its key is set.

Providers that are off by default need their own switch too: VENUS_LIVE_VERDA=1, VENUS_LIVE_META=1,
VENUS_LIVE_NVIDIA=1, VENUS_LIVE_GEMINI=1. Keys come from the shell, then VENUS_ENV_FILE, then the root .env, then
venus/.env. Run with the Venus environment, printing the results:

    cd tests/live && VENUS_LIVE=1 ../../venus/.venv/bin/python -m pytest -q -rs -s
"""
import os
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "venus"))

from venus.envfile import load_env  # noqa: E402

for candidate in (os.environ.get("VENUS_ENV_FILE"), ROOT / ".env", ROOT / "venus" / ".env"):
    if candidate and Path(candidate).is_file():
        load_env(candidate)
        break

TOY_PLUGIN = ROOT / "venus" / "tests" / "fixtures" / "toy_plugin"


def need(*keys, switch=None):
    """Skip unless live calls are on, the provider's own switch (if any) is on, and every key is set."""
    if os.environ.get("VENUS_LIVE") != "1":
        pytest.skip("live calls are off (set VENUS_LIVE=1)")
    if switch and os.environ.get(switch) != "1":
        pytest.skip(f"provider is off by default (set {switch}=1)")
    missing = [k for k in keys if not any(os.environ.get(name) for name in k.split("|"))]
    if missing:
        pytest.skip(f"missing key(s): {', '.join(missing)}")


class Counter:
    """An httpx.Client whose requests are counted (real HTTP calls only; cache hits never reach it)."""

    def __init__(self, timeout=60.0):
        self.count = 0
        self.client = httpx.Client(timeout=timeout, event_hooks={"request": [self._hit]})

    def _hit(self, request):
        self.count += 1


@pytest.fixture
def counter():
    c = Counter()
    yield c
    c.client.close()
