"""`python -m venus export`: write a standalone run-only agent folder (shared_context.md Section 4.1).

    <out>/leadline_agent/      copy of venus/agent (run-time code only; imports nothing from venus)
    <out>/plugins/<id>/        plugin files minus the checker module, gate.py and caches
    <out>/strategies/          the chosen validated strategies, base_model switched to Verda Nemotron by default
    <out>/requirements.txt     jsonschema, openai, httpx (+ anthropic only if an exported strategy needs it)
    <out>/README.md            env vars, usage, and which model each strategy was trained and validated on
    <out>/export.json          what was exported (also marks the folder as an export, so a re-export may replace it)

Nothing is written unless every check passes: plugins exist, each strategy is validated, made for that plugin version
and has valid settings, and the target is empty or an earlier export. The new folder is built next to the target and
swapped in at the end."""
import ast
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .agent.config import DEFAULT_PROVIDER, PRESETS, PROVIDERS
from .agent.errors import VenusError
from .agent.plugin import load_plugins
from .agent.request import VENUS_VERSION, run_strategy
from .agent.strategy import StrategyStore

AGENT_SRC = Path(__file__).resolve().parent / "agent"
MARKER = "export.json"
VERDA_NEMOTRON = {"model": "nemotron", "provider": "verda"}
# Same pins as pyproject.toml (tests/test_export.py checks they match).
REQUIREMENTS = {"jsonschema": "jsonschema>=4.23,<5", "openai": "openai>=2.54,<3", "httpx": "httpx>=0.28,<0.29",
                "anthropic": "anthropic>=2.8,<3"}
SKIP = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", "tests")


class ExportError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code, self.message = code, message


def export(plugin_ids, strategies_dir, out, *, plugins_dir=None, strategy_ids=None, package="leadline_agent",
           base_model=VERDA_NEMOTRON, fallback_provider=None) -> dict:
    """Write the agent folder at `out` and return its manifest. `strategy_ids` default: "<plugin>-default" for each
    plugin. `base_model=None` keeps each strategy's trained base model. `fallback_provider` (a provider name) ships
    that provider's client library so `VENUS_FALLBACK_PROVIDER=<it>` works in the exported folder. Raises ExportError
    and writes nothing when a check fails."""
    strategies_dir = Path(strategies_dir)
    plugins_dir = Path(plugins_dir) if plugins_dir is not None else strategies_dir.parent / "plugins"
    out = Path(out)
    if not package.isidentifier():
        raise ExportError("export_bad_package", f"package name {package!r} is not a Python identifier")
    if fallback_provider is not None and fallback_provider not in PROVIDERS:
        raise ExportError("export_bad_fallback", f"unknown fallback provider {fallback_provider!r}; known: "
                                                 f"{sorted(PROVIDERS)}")
    _check_out(out)
    _check_agent_imports()

    try:
        plugins = load_plugins(plugins_dir, runtime_only=True) if plugins_dir.is_dir() else {}
        chosen = []
        for pid in plugin_ids:
            if pid not in plugins:
                raise ExportError("plugin_not_found", f"no plugin named {pid!r} in {plugins_dir}")
        store = StrategyStore(strategies_dir)
        for sid in strategy_ids or [f"{pid}-default" for pid in plugin_ids]:
            raw = store.get(sid)  # strategy_not_found
            if raw.plugin not in plugin_ids:
                raise ExportError("strategy_plugin_mismatch", f"strategy {sid!r} is for {raw.plugin!r}, which is "
                                                               f"not exported ({', '.join(plugin_ids)})")
            chosen.append(run_strategy(plugins[raw.plugin], store, sid))  # validated, plugin version, settings
    except VenusError as e:
        raise ExportError(e.code, e.message) from None

    out.parent.mkdir(parents=True, exist_ok=True)  # built next to the target, so the final rename stays on one disk
    tmp = Path(tempfile.mkdtemp(prefix=f".{out.name}.", dir=out.parent))
    try:
        shutil.copytree(AGENT_SRC, tmp / package, ignore=SKIP)
        for pid in plugin_ids:
            _copy_plugin(plugins[pid], tmp / "plugins" / pid)
        (tmp / "strategies").mkdir()
        trained, providers = {}, set()
        for s in chosen:
            data = json.loads((strategies_dir / f"{s.id}.json").read_text(encoding="utf-8"))
            trained[s.id] = data["base_model"]
            if base_model is not None:
                data["base_model"] = dict(base_model)
            providers.add(_provider(data["base_model"]))
            (tmp / "strategies" / f"{s.id}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                                                             encoding="utf-8")
        if fallback_provider is not None:
            providers.add(fallback_provider)
        needs_anthropic = any(PROVIDERS.get(p, {}).get("client") == "anthropic" for p in providers)
        libs = ["jsonschema", "openai", "httpx"] + (["anthropic"] if needs_anthropic else [])
        (tmp / "requirements.txt").write_text("".join(REQUIREMENTS[n] + "\n" for n in libs), encoding="utf-8")
        manifest = {"venus_version": VENUS_VERSION, "package": package, "plugins": list(plugin_ids),
                    "strategies": [s.id for s in chosen], "base_model": base_model, "trained_base_models": trained,
                    "fallback_provider": fallback_provider, "requirements": libs,
                    "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        (tmp / "README.md").write_text(_readme(manifest), encoding="utf-8")
        (tmp / MARKER).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        _check_result(tmp, manifest)
        if out.exists():
            shutil.rmtree(out)  # empty, or an earlier export (checked by _check_out)
        tmp.rename(out)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return manifest


def _check_out(out: Path) -> None:
    if out.exists() and not out.is_dir():
        raise ExportError("export_out_not_empty", f"{out} is a file")
    if out.is_dir() and any(out.iterdir()) and not (out / MARKER).is_file():
        raise ExportError("export_out_not_empty", f"{out} is not empty and is not an earlier export (no {MARKER}); "
                                                  "pick an empty folder")


def _check_agent_imports() -> None:
    """The copied package must not import venus (it would not exist next to the export)."""
    for path in AGENT_SRC.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = ([a.name for a in node.names] if isinstance(node, ast.Import)
                     else [node.module or ""] if isinstance(node, ast.ImportFrom) and node.level == 0 else [])
            if any(n.split(".")[0] == "venus" for n in names):
                raise ExportError("export_bad_import", f"{path.relative_to(AGENT_SRC)} imports venus")


def _copy_plugin(plugin, dst: Path) -> None:
    checker_module = plugin_checker_module(plugin.root)
    skip = {"gate.py", "__pycache__"} | ({checker_module + ".py"} if checker_module else set())

    def ignore(folder, names):
        return [n for n in names if n in skip or n.endswith(".pyc") or n in (".pytest_cache", "tests")]
    shutil.copytree(plugin.root, dst, ignore=ignore)


def plugin_checker_module(root: Path) -> str | None:
    ref = json.loads((Path(root) / "plugin.json").read_text(encoding="utf-8")).get("checker") or ""
    module = ref.split(":")[0]
    return module.replace(".", "/") if module else None


def _provider(base_model: dict) -> str:
    preset = PRESETS.get(base_model.get("model", ""))
    return base_model.get("provider") or (preset[2] if preset and len(preset) > 2 else None) or DEFAULT_PROVIDER


def _check_result(root: Path, manifest: dict) -> None:
    """Load the written folder the way the agent will, so an export the agent would refuse never lands."""
    try:
        plugins = load_plugins(root / "plugins", runtime_only=True)
        store = StrategyStore(root / "strategies")
        for sid in manifest["strategies"]:
            s = store.get(sid)
            run_strategy(plugins[s.plugin], store, sid)
    except VenusError as e:
        raise ExportError("export_check_failed", f"the written folder does not load: {e.code}: {e.message}") from None


def _readme(m: dict) -> str:
    pkg = m["package"]
    rows = "\n".join(f"| `{sid}` | `{json.dumps(m['trained_base_models'][sid])}` |" for sid in m["strategies"])
    target = json.dumps(m["base_model"]) if m["base_model"] else "the trained base model (kept)"
    fb = m.get("fallback_provider")
    fallback = (f"\nThis folder ships the `{fb}` client for the fallback: set `VENUS_FALLBACK_PROVIDER={fb}` (and its "
                f"key) to retry once on `{fb}` when the primary model fails.\n" if fb else "")
    measured = ("Their scores were measured on the trained model; on the target model they are unmeasured."
                if m["base_model"] else "They run on the model they were scored on.")
    return f"""# {pkg}: standalone run-only agent

Exported by `python -m venus export` on {m['created_at']} (venus_version {m['venus_version']}).
Plugins: {', '.join(f'`{p}`' for p in m['plugins'])}. Run mode only: no training, no server, no FastAPI.

## Install and run

```bash
pip install -r requirements.txt
```

```python
import sys
sys.path.insert(0, "/path/to/this/folder")
from {pkg} import Agent, AgentError

agent = Agent("/path/to/this/folder")
resp = agent.run("<plugin id>", input_data, trace_id=tid, on_cala_result=db.cala_hook(trace_id=tid))
# resp["status"] is "ok" or "error"; run() never raises for run problems. Contract: shared_context.md Section 4.2.
```

## Environment

| Variable | Use |
|---|---|
| `VERDA_API_KEY`, `VERDA_BASE_URL` | Verda endpoint for the `verda` provider |
| `VENUS_NEMOTRON_MODEL` | model id for the `nemotron` preset (`nemotron-3.5-super-vl` on Verda) |
| `NVIDIA_API_KEY` (`NVIDIA_BASE_URL` optional) | NVIDIA endpoint, when the fallback provider is `nvidia` |
| `ANTHROPIC_API_KEY`, `VENUS_CLAUDE_RESEARCH_MODEL` | Anthropic endpoint and the `claude-research` model id, when the fallback provider is `anthropic` |
| `VENUS_FALLBACK_PROVIDER`, `VENUS_FALLBACK_MODEL` | provider (`anthropic` or `nvidia`) + model id or preset (default: `claude-research` / the NVIDIA Nemotron id): one retry when the primary model is down, times out or is misconfigured |
| `VENUS_MODEL_TIMEOUT` | seconds per model call; Verda clients wait at least 120 s (cold starts) |
| `VENUS_MAX_TOKENS` | answer room on verda/nvidia (default 8192, at most 32768) |
| `CALA_API_KEY`, `VENUS_CALA_MAX_CALLS`, `VENUS_CALA_CACHE_DIR` | Cala tools for plugins with `"cala": true` (cap per run, default 3) |
| `CONTEXT_DEV_API_KEY` | web tools; without it runs still work, with a warning |

The agent never reads `.env` files: set these in the process environment or pass `environ=` to `Agent`.
{fallback}
## Strategies

Exported strategies run on {target}. {measured} They were trained and validated on:

| Strategy | Trained base model |
|---|---|
{rows}

A strategy validated on one model is not automatically as good on another: check the scores on the new model before
relying on them.
"""
