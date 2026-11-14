import subprocess
import sys

import venus
from conftest import ROOT

STABLE = ["Venus", "create_app", "handle_file", "check_request", "load_plugin", "load_plugins", "StrategyStore",
          "Strategy", "Tendency", "Plugin", "Score", "run_case", "RunResult", "train", "Tool", "collect_tools",
          "web_tools", "ContextDev", "ModelClient", "resolve_model", "FakeModel", "fake_text", "fake_tool_call",
          "Budget", "VenusError", "load_env", "load_schema", "VENUS_VERSION"]


def test_stable_names_exported():
    missing = [n for n in STABLE if n not in venus.__all__ or not hasattr(venus, n)]
    assert missing == []
    assert all(hasattr(venus, n) for n in venus.__all__)


def test_import_does_not_load_fastapi():
    code = "import sys, venus; print('fastapi' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd="/", check=True)
    assert out.stdout.strip() == "False"


def test_example_script_runs_offline():
    out = subprocess.run([sys.executable, str(ROOT / "examples" / "use_venus.py")], capture_output=True, text=True,
                         cwd=ROOT, timeout=60)
    assert out.returncode == 0, out.stderr
    assert '"label": "negative"' in out.stdout and '"mode": "training"' in out.stdout
