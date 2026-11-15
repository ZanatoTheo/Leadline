"""engine: the bundled agent's run-time names, so the service starts without the venus package."""
import subprocess
import sys
from pathlib import Path

LEADLINE = Path(__file__).resolve().parents[1]
NAMES = ("load_plugin", "run_case", "FakeModel", "fake_text", "fake_tool_call", "InputError", "Cala", "cala_tools")


def test_engine_names_come_from_the_bundled_agent():
    import engine

    for name in NAMES:
        assert getattr(engine, name).__module__.startswith("leadline_agent."), name


def test_agent_root_is_picked_at_first_use_not_at_import():
    """serve.py reads --env-file after its imports, so LEADLINE_AGENT_DIR from that file must still count."""
    code = ("import sys, serve\n"
            "assert 'leadline_agent' not in sys.modules, 'leadline_agent imported at import time'\n")
    out = subprocess.run([sys.executable, "-c", code], cwd=LEADLINE, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-2000:]


def test_agent_dir_set_after_import_is_used(tmp_path):
    package = tmp_path / "agent" / "leadline_agent"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "plugin.py").write_text("def load_plugin(path):\n    return 'from-env-root'\n")
    code = ("import os, sys, engine, runtime\n"
            f"os.environ['LEADLINE_AGENT_DIR'] = {str(tmp_path / 'agent')!r}\n"
            "assert engine.load_plugin('x') == 'from-env-root'\n"
            "assert engine.agent_root() == runtime.Path(os.environ['LEADLINE_AGENT_DIR']).resolve()\n")
    env = {k: v for k, v in __import__("os").environ.items() if k != "LEADLINE_AGENT_DIR"}
    out = subprocess.run([sys.executable, "-c", code], cwd=LEADLINE, capture_output=True, text=True, timeout=60, env=env)
    assert out.returncode == 0, out.stderr[-2000:]


def test_agent_root_follows_runtime_default(monkeypatch, tmp_path):
    import engine
    import runtime

    monkeypatch.delenv("LEADLINE_AGENT_DIR", raising=False)
    monkeypatch.setattr(runtime, "DEFAULT_AGENT_DIR", tmp_path)
    assert engine.agent_root() == tmp_path.resolve()


def test_service_modules_load_without_venus():
    code = ("import sys, serve\n"
            "bad = sorted(m for m in sys.modules if m == 'venus' or m.startswith('venus.'))\n"
            "assert not bad, bad\n")
    out = subprocess.run([sys.executable, "-c", code], cwd=LEADLINE, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-2000:]
