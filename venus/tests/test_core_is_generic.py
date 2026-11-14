"""The core must know nothing about any task: no module in venus/ may import a plugin."""
import ast
from pathlib import Path

CORE = Path(__file__).resolve().parent.parent / "venus"


def imported_roots(path):
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.module.split(".")[0]


def test_core_never_imports_plugins():
    files = list(CORE.rglob("*.py"))
    assert files, "no core modules found"
    offenders = [str(f) for f in files if "plugins" in set(imported_roots(f))]
    assert offenders == []
