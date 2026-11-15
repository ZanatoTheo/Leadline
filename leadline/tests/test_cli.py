"""JSON command-line boundary for the Leadline runtime."""
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_cli_dispatches_json_to_handler_and_writes_one_json_result():
    from cli import dispatch

    seen = []

    def handler(payload):
        seen.append(payload)
        return {"ok": True, "echo": payload}

    result = dispatch({"command": "ping", "payload": {"value": 3}}, handlers={"ping": handler})

    assert seen == [{"value": 3}]
    assert result == {"ok": True, "echo": {"value": 3}}


def test_cli_module_reads_one_json_command_and_writes_json():
    proc = subprocess.run(
        [sys.executable, "-m", "leadline", "--help"], cwd=ROOT.parent,
        input="", text=True, capture_output=True, check=False,
    )
    assert proc.returncode == 0
    assert "JSON" in proc.stdout


def test_cli_rejects_unknown_commands():
    from cli import dispatch

    try:
        dispatch({"command": "unknown", "payload": {}} , handlers={})
    except ValueError as exc:
        assert "unknown command" in str(exc)
    else:
        raise AssertionError("unknown command was accepted")
