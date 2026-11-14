"""Run-time code must not import training or server code.

These modules live in `venus.agent` (phase 10), which `venus export` copies as a standalone package whose only
dependencies are ALLOWED_THIRD_PARTY. The old `venus.<name>` imports still work and are the same module objects."""
import ast
import importlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "venus" / "agent"

MOVED = {"cala", "runner", "models", "tools", "web", "plugin", "strategy", "cache", "budget", "config", "errors",
         "tendency", "fake", "envfile", "request", "schemas", "anthropic_client"}
RUNTIME = MOVED | {"core"}  # core: the Agent class (new in venus.agent, no old name)

# Outside libraries run-time code may import; the exported agent's requirements.txt lists exactly these.
ALLOWED_THIRD_PARTY = {"jsonschema", "openai", "httpx", "anthropic"}  # anthropic: added 2026-11-14 (Leadline plan, phase 1)


def module_path(name):
    if name == "schemas":
        return CORE / "schemas" / "__init__.py"
    return CORE / f"{name}.py"


def bad_imports(path):
    """Imports in `path` (anywhere, including inside functions) that are not stdlib, ALLOWED_THIRD_PARTY or a
    run-time sibling. Relative imports are reported as ".name" (or "..name" for a parent package); dynamic imports
    (`importlib.import_module`, `__import__`) are always reported, since their target can't be checked."""
    bad = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if name in ("import_module", "__import__"):
                bad.append(f"{name}()")
        elif isinstance(node, ast.ImportFrom) and node.level > 1:  # outside the package
            dots = "." * node.level
            bad.extend([dots + node.module] if node.module else [dots + a.name for a in node.names])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root not in sys.stdlib_module_names and root not in ALLOWED_THIRD_PARTY:
                    bad.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                root = (node.module or "").split(".")[0]
                if root not in sys.stdlib_module_names and root not in ALLOWED_THIRD_PARTY:
                    bad.append(node.module)
            elif node.module:  # from .x import y
                if node.module.split(".")[0] not in RUNTIME:
                    bad.append("." + node.module)
            else:  # from . import x, y
                bad.extend("." + alias.name for alias in node.names if alias.name not in RUNTIME)
    return bad


def test_runtime_modules_exist():
    missing = [name for name in sorted(RUNTIME) if not module_path(name).is_file()]
    assert missing == [], f"run-time modules not found (renamed? update RUNTIME): {missing}"


def test_runtime_imports_stay_runtime():
    offenders = {name: bad_imports(module_path(name)) for name in sorted(RUNTIME)}
    offenders = {name: bad for name, bad in offenders.items() if bad}
    assert offenders == {}, f"run-time modules import non-run-time code: {offenders}"


def test_checker_catches_bad_imports(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text(
        "import json\n"
        "from .errors import VenusError\n"
        "from .training import train\n"
        "from . import serve\n"
        "import fastapi\n"
        "from .schemas import load_schema\n"
        "from .schemas.extra import thing\n"
        "from .. import outside\n"
        "from ..runner import run_case\n"
        "import importlib\n"
        "def later():\n"
        "    import uvicorn\n"
        "    importlib.import_module('venus.training')\n"
        "    __import__('venus.serve')\n"
    )
    assert sorted(bad_imports(bad)) == sorted([
        ".training", ".serve", "fastapi", "..outside", "..runner", "uvicorn",
        "import_module()", "__import__()",
    ])


def test_agent_package_init_stays_runtime():
    assert bad_imports(CORE / "__init__.py") == []


def test_old_import_paths_are_the_same_modules():
    """`venus.runner` and `venus.agent.runner` are one module: a monkeypatch on either one is seen by both."""
    different = [name for name in sorted(MOVED)
                 if importlib.import_module(f"venus.{name}") is not importlib.import_module(f"venus.agent.{name}")]
    assert different == []


def test_importing_the_agent_loads_no_server_or_training_code():
    code = ("import sys; sys.path.insert(0, sys.argv[1]); import venus.agent; from venus.agent import Agent; "
            "print([m for m in ('venus.serve', 'venus.training', 'venus.gate', 'fastapi', 'uvicorn') "
            "if m in sys.modules])")
    out = subprocess.run([sys.executable, "-I", "-c", code, str(ROOT)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "[]"
