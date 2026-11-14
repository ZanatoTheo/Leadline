"""`python -m venus export` (J3, shared_context.md Section 4.1): a standalone agent folder with `leadline_agent/`,
runtime plugin files, validated strategies only, requirements.txt, README.md. Offline: toy plugin + FakeModel."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from venus.__main__ import main
from venus.export import ExportError, export

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT.parent
GOOD = json.dumps({"output": {"label": "positive"}, "sources": []})


def strategy(sid, status="validated", base_model=None, plugin="toy-sentiment"):
    return {"id": sid, "plugin": plugin, "plugin_version": "1.0.0", "status": status,
            "base_model": base_model or {"model": "claude-research", "provider": "anthropic"}, "tendencies": [
                {"id": "t-1", "text": "Read the whole text first."}], "created_at": "2026-11-14T00:00:00Z"}


@pytest.fixture
def src(tmp_path, toy_plugin_dir):
    """A source tree: plugins/toy-sentiment (with checker.py, gate.py and a helper) + strategies/ (default + draft)."""
    def make(strategies=None):
        base = tmp_path / "src"
        plugin = base / "plugins" / "toy-sentiment"
        shutil.copytree(toy_plugin_dir, plugin, ignore=shutil.ignore_patterns("__pycache__"))
        (plugin / "gate.py").write_text("def gate(settings, cases):\n    return {'passed': True}\n")
        (plugin / "helper.py").write_text("VALUE = 1\n")
        sdir = base / "strategies"
        sdir.mkdir()
        for s in strategies or [strategy("toy-sentiment-default"), strategy("toy-sentiment-draft-1", "draft")]:
            (sdir / f"{s['id']}.json").write_text(json.dumps(s))
        return base
    return make


def do_export(base, out, **kw):
    return export(["toy-sentiment"], base / "strategies", out, **kw)


def test_layout_is_standalone(src, tmp_path):
    out = tmp_path / "out"
    manifest = do_export(src(), out)
    pkg = out / "leadline_agent"
    assert (pkg / "__init__.py").is_file() and (pkg / "core.py").is_file() and (pkg / "runner.py").is_file()
    assert sorted(p.name for p in (pkg / "schemas").glob("*.json")) == [
        "plugin.schema.json", "request.schema.json", "response.schema.json", "strategy.schema.json"]
    names = {p.name for p in pkg.rglob("*")}
    assert not names & {"serve.py", "training.py", "gate.py", "export.py", "__main__.py", "__pycache__"}
    plugin_files = {p.name for p in (out / "plugins" / "toy-sentiment").iterdir()}
    assert plugin_files == {"plugin.json", "input.schema.json", "output.schema.json", "helper.py"}
    assert [p.name for p in (out / "strategies").iterdir()] == ["toy-sentiment-default.json"]
    assert manifest["strategies"] == ["toy-sentiment-default"]
    assert json.loads((out / "export.json").read_text())["plugins"] == ["toy-sentiment"]


def test_requirements_list_only_runtime_libraries(src, tmp_path):
    out = tmp_path / "out"
    do_export(src(), out)
    reqs = (out / "requirements.txt").read_text().split()
    assert [r.split(">")[0].split("=")[0] for r in reqs] == ["jsonschema", "openai", "httpx"]
    assert all(">=" in r for r in reqs)


def test_readme_names_the_env_vars(src, tmp_path):
    out = tmp_path / "out"
    do_export(src(), out)
    text = (out / "README.md").read_text()
    for var in ("VERDA_API_KEY", "VERDA_BASE_URL", "VENUS_NEMOTRON_MODEL", "NVIDIA_API_KEY", "CALA_API_KEY",
                "CONTEXT_DEV_API_KEY", "VENUS_MODEL_TIMEOUT", "VENUS_FALLBACK_PROVIDER"):
        assert var in text, var
    assert "toy-sentiment-default" in text and "claude-research" in text  # the trained base model is recorded


def test_strategies_target_verda_nemotron_and_keep_their_trained_model_in_the_manifest(src, tmp_path):
    out = tmp_path / "out"
    manifest = do_export(src(), out)
    s = json.loads((out / "strategies" / "toy-sentiment-default.json").read_text())
    assert s["base_model"] == {"model": "nemotron", "provider": "verda"} and s["status"] == "validated"
    assert manifest["trained_base_models"]["toy-sentiment-default"] == {"model": "claude-research",
                                                                        "provider": "anthropic"}


def test_keep_base_model_keeps_it_and_adds_anthropic_when_needed(src, tmp_path):
    out = tmp_path / "out"
    do_export(src(), out, base_model=None)
    s = json.loads((out / "strategies" / "toy-sentiment-default.json").read_text())
    assert s["base_model"]["provider"] == "anthropic"
    assert "anthropic" in [r.split(">")[0] for r in (out / "requirements.txt").read_text().split()]


@pytest.mark.parametrize("strategies,ids,code", [
    ([strategy("toy-sentiment-default", "draft")], None, "strategy_not_validated"),
    ([strategy("toy-sentiment-default")], ["toy-sentiment-draft-1"], "strategy_not_found"),
])
def test_refuses_drafts_and_missing_strategies_and_writes_nothing(src, tmp_path, strategies, ids, code):
    out = tmp_path / "out"
    with pytest.raises(ExportError) as e:
        do_export(src(strategies), out, strategy_ids=ids)
    assert e.value.code == code and not out.exists()


def test_refuses_an_unknown_plugin(src, tmp_path):
    with pytest.raises(ExportError) as e:
        export(["nope"], src() / "strategies", tmp_path / "out")
    assert e.value.code == "plugin_not_found"


def test_refuses_a_non_empty_folder_that_is_not_an_export_but_replaces_an_old_export(src, tmp_path):
    base = src()
    busy = tmp_path / "busy"
    busy.mkdir()
    (busy / "notes.txt").write_text("mine")
    with pytest.raises(ExportError) as e:
        do_export(base, busy)
    assert e.value.code == "export_out_not_empty" and (busy / "notes.txt").read_text() == "mine"
    out = tmp_path / "out"
    do_export(base, out)
    (out / "strategies" / "stale.json").write_text("{}")
    do_export(base, out)
    assert not (out / "strategies" / "stale.json").exists()


def test_exported_agent_runs_isolated_without_venus(src, tmp_path):
    out = tmp_path / "out"
    do_export(src(), out)
    code = (
        "import json, sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "from leadline_agent import Agent\n"
        "from leadline_agent.fake import FakeModel, fake_text\n"
        f"model = FakeModel([fake_text({GOOD!r})])\n"
        "agent = Agent(sys.argv[1], model=model, web_tools=[], cala=False, environ={})\n"
        "resp = agent.run('toy-sentiment', {'text': 'great'})\n"
        "loaded = [m for m in ('venus', 'fastapi', 'uvicorn', 'anthropic') if m in sys.modules]\n"
        "print(json.dumps({'status': resp['status'], 'output': resp['outputs'][0]['output'], 'loaded': loaded}))\n")
    run = subprocess.run([sys.executable, "-I", "-c", code, str(out)], capture_output=True, text=True, timeout=60,
                         cwd=tmp_path)
    assert run.returncode == 0, run.stderr
    result = json.loads(run.stdout)
    assert result == {"status": "ok", "output": {"label": "positive"}, "loaded": []}


def test_cli_exports_and_exits_2_on_refusal(src, tmp_path, capsys):
    base = src()
    args = ["export", "--plugins", "toy-sentiment", "--strategies", str(base / "strategies")]
    assert main(args + ["--out", str(tmp_path / "out")]) == 0
    assert json.loads(capsys.readouterr().out)["strategies"] == ["toy-sentiment-default"]
    assert main(args + ["--out", str(tmp_path / "out2"), "--strategy", "toy-sentiment-draft-1"]) == 2
    assert "strategy_not_validated" in capsys.readouterr().err


def test_exports_the_real_leadline_plugins(tmp_path):
    """The Phase 10 command on the repo's own files (read only), plugins dir found next to the strategies dir."""
    out = tmp_path / "leadline-agent"
    manifest = export(["leadline-profile", "leadline-match"], REPO / "leadline" / "strategies", out)
    assert manifest["strategies"] == ["leadline-profile-default", "leadline-match-default"]
    assert (out / "plugins" / "leadline-match" / "prefilter.py").is_file()
    assert not (out / "plugins" / "leadline-match" / "gate.py").exists()
    assert not (out / "plugins" / "leadline-profile" / "checker.py").exists()
    code = ("import json, sys\nsys.path.insert(0, sys.argv[1])\nfrom leadline_agent import Agent\n"
            "a = Agent(sys.argv[1], web_tools=[], cala=False, environ={})\n"
            "print(json.dumps(sorted(a.settings('leadline-match'))))\n")
    run = subprocess.run([sys.executable, "-I", "-c", code, str(out)], capture_output=True, text=True, timeout=60,
                         cwd=tmp_path)
    assert run.returncode == 0, run.stderr
    assert isinstance(json.loads(run.stdout), list)


def test_requirement_pins_match_pyproject():
    import tomllib
    from venus.export import REQUIREMENTS
    deps = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["dependencies"]
    pinned = {d.split(">")[0].split("=")[0].split("<")[0]: d for d in deps}
    assert {name: pinned[name] for name in REQUIREMENTS} == REQUIREMENTS


# --- fallback provider: its client library ships and the README says how to turn it on ---------------------------

def test_fallback_provider_adds_its_client_library_and_is_documented(src, tmp_path):
    out = tmp_path / "out"
    manifest = do_export(src(), out, fallback_provider="anthropic")
    reqs = (out / "requirements.txt").read_text().split()
    assert [r.split(">")[0] for r in reqs] == ["jsonschema", "openai", "httpx", "anthropic"]
    assert manifest["fallback_provider"] == "anthropic"
    text = (out / "README.md").read_text()
    assert "VENUS_FALLBACK_PROVIDER=anthropic" in text and "ANTHROPIC_API_KEY" in text
    assert "unmeasured" in text  # strategies run on a model other than the one they were scored on


def test_refuses_an_unknown_fallback_provider_and_writes_nothing(src, tmp_path):
    out = tmp_path / "out"
    with pytest.raises(ExportError) as e:
        do_export(src(), out, fallback_provider="nope")
    assert e.value.code == "export_bad_fallback" and not out.exists()


def test_cli_fallback_provider(src, tmp_path, capsys):
    base = src()
    out = tmp_path / "out"
    assert main(["export", "--plugins", "toy-sentiment", "--strategies", str(base / "strategies"), "--out", str(out),
                 "--fallback-provider", "anthropic"]) == 0
    assert json.loads(capsys.readouterr().out)["fallback_provider"] == "anthropic"
    assert "anthropic" in (out / "requirements.txt").read_text()
