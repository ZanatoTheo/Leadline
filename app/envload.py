"""Load the nearest project .env file without replacing shell settings."""

from __future__ import annotations

import os
from pathlib import Path


def _find_env_file() -> Path | None:
    """Return the first .env found from this module's folder up to the filesystem root."""
    for folder in Path(__file__).resolve().parents:
        candidate = folder / ".env"
        if candidate.is_file():
            return candidate
    return None


def _parse(path: Path) -> dict[str, str]:
    values = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or not key or not (key[0].isalpha() or key[0] == "_"):
            continue
        if not all(char.isalnum() or char == "_" for char in key):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].rstrip()
        values[key] = value
    return values


def load_env() -> dict[str, str]:
    """Load the nearest .env; existing process variables take precedence.

    Returns the values from the file merged with the current process values for
    those keys. A missing file is allowed.
    """
    path = _find_env_file()
    if path is None:
        return {}
    file_values = _parse(path)
    for key, value in file_values.items():
        os.environ.setdefault(key, value)
    return {key: os.environ[key] for key in file_values}
