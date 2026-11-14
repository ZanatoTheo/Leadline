"""The JSON Schemas of Venus's contract: plugin manifest, strategy file, request and response."""
import json
from functools import lru_cache
from pathlib import Path

SCHEMA_DIR = Path(__file__).resolve().parent
NAMES = ("plugin", "strategy", "request", "response")


@lru_cache(maxsize=None)
def _load(name: str) -> str:
    if name not in NAMES:
        raise KeyError(f"unknown schema {name!r}; known: {', '.join(NAMES)}")
    return (SCHEMA_DIR / f"{name}.schema.json").read_text()


def load_schema(name: str) -> dict:
    """A fresh copy of the named schema (callers may change it safely)."""
    return json.loads(_load(name))
