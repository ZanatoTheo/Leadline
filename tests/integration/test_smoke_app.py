"""The offline smoke run (scripts/smoke_app.py) and its outbound guards.

The guard tests always run; they point at an unroutable TEST-NET address and an `.invalid` name, so nothing leaves the
machine even if a guard is broken. The full smoke run builds and starts the app (minutes), so it runs only with
LEADLINE_SMOKE=1:

    LEADLINE_SMOKE=1 venus/.venv/bin/python -m pytest -q tests/integration/test_smoke_app.py
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / "venus" / ".venv" / "bin" / "python"
NODE = shutil.which("node")


def test_python_guard_blocks_connect_and_dns(tmp_path):
    log = tmp_path / "outbound.log"
    code = (
        "import socket\n"
        "for target in (lambda: socket.create_connection(('192.0.2.1', 443), timeout=1),\n"
        "               lambda: socket.getaddrinfo('api.example.invalid', 443),\n"
        "               lambda: socket.gethostbyname('api.example.invalid')):\n"
        "    try:\n"
        "        target()\n"
        "    except OSError as e:\n"
        "        print('blocked' if 'smoke guard' in str(e) else f'other: {e}')\n"
        "s = socket.socket(); s.bind(('127.0.0.1', 0)); s.listen(); c = socket.create_connection(s.getsockname())\n"
        "print('local ok')\n"
    )
    out = subprocess.run([str(PYTHON), "-c", code], capture_output=True, text=True, timeout=30,
                         env={**os.environ, "PYTHONPATH": str(ROOT / "scripts" / "smoke_pyguard"),
                              "SMOKE_OUTBOUND_LOG": str(log)})
    assert out.stdout.split() == ["blocked", "blocked", "blocked", "local", "ok"], out.stdout + out.stderr
    lines = log.read_text().splitlines()
    assert len(lines) == 3 and "192.0.2.1" in lines[0] and all("api.example.invalid" in x for x in lines[1:])


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_node_guard_blocks_fetch(tmp_path):
    log = tmp_path / "outbound.log"
    code = (
        "fetch('http://192.0.2.1/', {signal: AbortSignal.timeout(3000)})"
        ".then(() => console.log('reached'), () => console.log('failed'))"
        ".then(() => require('dns').lookup('api.example.invalid', (e) => console.log(e ? 'dns failed' : 'dns ok')));"
    )
    out = subprocess.run([NODE, "--require", str(ROOT / "scripts" / "smoke_guard.cjs"), "-e", code],
                         capture_output=True, text=True, timeout=30, env={**os.environ, "SMOKE_OUTBOUND_LOG": str(log)})
    assert out.stdout.split() == ["failed", "dns", "failed"], out.stdout + out.stderr
    lines = log.read_text().splitlines()
    assert any("192.0.2.1" in x for x in lines) and any("api.example.invalid" in x for x in lines), lines


@pytest.mark.skipif(os.environ.get("LEADLINE_SMOKE") != "1", reason="set LEADLINE_SMOKE=1 to run the full smoke run")
def test_smoke_app_all_routes_offline():
    proc = subprocess.Popen([str(PYTHON), str(ROOT / "scripts" / "smoke_app.py")], cwd=ROOT, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        stdout, stderr = proc.communicate(timeout=1200)
    except subprocess.TimeoutExpired:
        proc.terminate()  # SIGTERM: smoke_app stops its servers before exiting
        stdout, stderr = proc.communicate(timeout=60)
        pytest.fail(f"smoke run timed out:\n{stdout[-3000:]}")
    print(stdout[-4000:])
    assert proc.returncode == 0, stdout[-3000:] + stderr[-2000:]
    assert "outbound connections: 0" in stdout
    assert " FAIL " not in stdout
