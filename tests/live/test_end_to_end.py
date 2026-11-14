"""One whole Venus run for real: the toy plugin through `run_case` with real Context.dev web tools and the
`claude-fast` preset. Checks the first search happens (or is warned about), the output passes the schema, and the
usage counts match what was spent. About 3-4 model calls and 1-3 web calls."""
import os

from conftest import TOY_PLUGIN, need

from venus.cache import DiskCache
from venus.plugin import load_plugin
from venus.runner import run_case
from venus.serve import default_model_factory
from venus.web import ContextDev, web_tools


def test_run_case_with_real_web_and_claude(counter, tmp_path):
    need("ANTHROPIC_API_KEY", "CONTEXT_DEV_API_KEY|CONTEXTDEV_API_KEY")
    plugin = load_plugin(TOY_PLUGIN)
    env = {k: v for k, v in os.environ.items() if k != "VENUS_MODEL_CACHE"}
    model = default_model_factory(max_model_calls=8, environ=env)({"model": "claude-fast"})
    tools = web_tools(ContextDev(http_client=counter.client, cache=DiskCache(tmp_path)))

    result = run_case(plugin, {"text": "Reviews of the Supercell game Clash Royale on launch were glowing."},
                      plugin.seed_tendencies, model, tools=tools, max_turns=4, max_web_calls=3)

    plugin.validate_output(result.output, path="output")
    searched = result.usage["web_calls"] > 0
    assert searched or any("no forced search" in w for w in result.warnings)
    assert result.usage["web_calls"] == counter.count  # every web call counted was a real request (fresh cache)
    assert result.usage["model_calls"] == model.budget.model_calls
    print(f"\nEND-TO-END output={result.output} searched={searched} usage={result.usage} "
          f"warnings={result.warnings} sources={result.sources[:3]}")
