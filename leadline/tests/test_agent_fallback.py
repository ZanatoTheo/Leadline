"""The injected agent copy (leadline/agent/leadline_agent) falls back to the fallback model when the primary model's
reply is cut off (model_bad_reply) or unusable (output_invalid). Leadline-only: Venus itself keeps no fallback on
output_invalid, so this copy differs until the next scripts/inject_agent.sh run."""
import importlib
import json
import shutil
import sys
from pathlib import Path

import pytest

AGENT_DIR = Path(__file__).resolve().parents[1] / "agent"
TOY = Path(__file__).resolve().parents[2] / "venus" / "tests" / "fixtures" / "toy_plugin"
GOOD = json.dumps({"output": {"label": "positive"}, "sources": []})
ENV = {"VERDA_BASE_URL": "https://verda.example/v1", "VENUS_NEMOTRON_MODEL": "nemotron-3.5-super-vl"}
FALLBACK = {"provider": "nvidia", "model": "nv-model"}

pytestmark = [
    pytest.mark.skipif(not (AGENT_DIR / "leadline_agent" / "__init__.py").is_file(),
                       reason="no injected agent (run scripts/inject_agent.sh)"),
    pytest.mark.skipif(not TOY.is_dir(), reason="no Venus toy plugin fixture"),
]


@pytest.fixture
def la(monkeypatch):
    """The real injected leadline_agent package (an earlier test may have cached a fake one)."""
    for name in [m for m in sys.modules if m == "leadline_agent" or m.startswith("leadline_agent.")]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.syspath_prepend(str(AGENT_DIR))
    core = importlib.import_module("leadline_agent.core")
    fake = importlib.import_module("leadline_agent.fake")
    errors = importlib.import_module("leadline_agent.errors")
    yield core, fake, errors
    # Drop the modules imported here, so later tests that load their own leadline_agent don't get this one.
    for name in [m for m in sys.modules if m == "leadline_agent" or m.startswith("leadline_agent.")]:
        del sys.modules[name]


@pytest.fixture
def root(tmp_path):
    plugin = tmp_path / "root" / "plugins" / "toy-sentiment"
    plugin.mkdir(parents=True)
    for f in TOY.iterdir():
        if f.is_file() and f.name != "checker.py":
            shutil.copy(f, plugin / f.name)
    strategies = tmp_path / "root" / "strategies"
    strategies.mkdir()
    (strategies / "toy-sentiment-default.json").write_text(json.dumps({
        "id": "toy-sentiment-default", "plugin": "toy-sentiment", "plugin_version": "1.0.0", "status": "validated",
        "base_model": {"model": "nemotron", "provider": "verda"}, "tendencies": [],
        "created_at": "2026-11-14T00:00:00Z"}))
    return tmp_path / "root"


def _agent(la, root, primary, fallback_answers, seen):
    core, fake, _ = la

    def make(base_model):
        seen.append(base_model.get("provider"))
        return fake.FakeModel(primary if base_model.get("provider") == "verda" else fallback_answers)
    return core.Agent(root, model_factory=make, web_tools=[], cala=False, environ=dict(ENV),
                      fallback_base_model=FALLBACK)


def _raise(la, code):
    _, _, errors = la

    def script(messages, tools, tool_choice):
        raise errors.ModelError(code, "boom")
    return script


def test_a_cut_off_reply_falls_back_once(la, root):
    seen = []
    resp = _agent(la, root, _raise(la, "model_bad_reply"), [la[1].fake_text(GOOD)], seen).run(
        "toy-sentiment", {"text": "x"})
    assert resp["status"] == "ok", resp
    assert resp["base_model"] == FALLBACK and seen == ["verda", "nvidia"]
    assert "fell back to nvidia: model_bad_reply" in resp["warnings"]


def test_an_unusable_answer_falls_back_once(la, root):
    seen = []
    bad = [la[1].fake_text("not json"), la[1].fake_text("still not json")]
    resp = _agent(la, root, bad, [la[1].fake_text(GOOD)], seen).run("toy-sentiment", {"text": "x"})
    assert resp["status"] == "ok", resp
    assert seen == ["verda", "nvidia"] and "fell back to nvidia: output_invalid" in resp["warnings"]


def test_a_failed_fallback_reports_the_primary_error(la, root):
    seen = []
    resp = _agent(la, root, _raise(la, "model_bad_reply"), _raise(la, "model_unavailable"), seen).run(
        "toy-sentiment", {"text": "x"})
    assert resp["status"] == "error" and resp["error"]["code"] == "model_bad_reply", resp
    assert seen == ["verda", "nvidia"]
    assert any(w.startswith("fallback to nvidia failed: model_unavailable") for w in resp["warnings"])
