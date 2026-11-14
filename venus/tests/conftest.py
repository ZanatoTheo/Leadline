import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
EXAMPLES = ROOT / "examples"


@pytest.fixture
def toy_plugin_dir():
    return FIXTURES / "toy_plugin"


@pytest.fixture
def strategies_dir():
    return FIXTURES / "strategies"


@pytest.fixture
def example():
    def load(name):
        return json.loads((EXAMPLES / name).read_text())
    return load


@pytest.fixture
def plugin_copy(tmp_path, toy_plugin_dir):
    """A writable copy of the toy plugin, for tests that break its files."""
    def make(**manifest_changes):
        dst = tmp_path / "plugin"
        dst.mkdir()
        for f in toy_plugin_dir.iterdir():
            if f.is_file():
                (dst / f.name).write_text(f.read_text())
        manifest = json.loads((dst / "plugin.json").read_text())
        for key, value in manifest_changes.items():
            if value is None:
                manifest.pop(key, None)
            else:
                manifest[key] = value
        (dst / "plugin.json").write_text(json.dumps(manifest))
        return dst
    return make
