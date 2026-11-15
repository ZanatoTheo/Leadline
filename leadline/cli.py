"""JSON stdin/stdout command boundary for Leadline."""
from __future__ import annotations

import json
import sys
from collections.abc import Callable, Mapping


def dispatch(command, *, handlers: Mapping[str, Callable] | None = None):
    if not isinstance(command, dict):
        raise ValueError("command must be a JSON object")
    name = command.get("command")
    payload = command.get("payload", {})
    if not isinstance(name, str) or not name:
        raise ValueError("command must be a non-empty string")
    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object")
    handler = (handlers or {}).get(name)
    if handler is None:
        raise ValueError(f"unknown command: {name}")
    return handler(payload)


def main(argv=None, *, handlers=None, stdin=None, stdout=None, stderr=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    stdin, stdout, stderr = stdin or sys.stdin, stdout or sys.stdout, stderr or sys.stderr
    if argv in (["--help"], ["-h"]):
        stdout.write("Leadline JSON CLI\nRead one {\\\"command\\\": ..., \\\"payload\\\": {...}} object from stdin.\n")
        return 0
    if argv:
        stderr.write("usage: python -m leadline [--help]\n")
        return 2
    try:
        result = dispatch(json.load(stdin), handlers=handlers)
        json.dump(result, stdout, separators=(",", ":"))
        stdout.write("\n")
        return 0
    except (ValueError, json.JSONDecodeError) as exc:
        stderr.write(json.dumps({"error": str(exc)}) + "\n")
        return 2
