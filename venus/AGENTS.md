# AGENTS.md: shared context for every agent working on Venus (read-only for lanes)

## What Venus is
A general-purpose engine. A **plugin** defines a task (brief, input/output JSON Schemas, a checker, optional tools).
A **strategy** is a base model plus **behavioral tendencies** (short instructions that shape how the agent acts) for
one plugin version. Venus never contains task-specific code: tasks live in `plugins/`, and `venus/` must not import
them (`tests/test_core_is_generic.py`).

## The one rule for requests
Every request is either:
- `mode: "training"`: `{venus_version: "1", plugin, mode, cases: [{id, input, expected}]}`. `expected` is the
  validated reference; Venus runs the base model on each `input` and scores it against `expected` with the checker.
- `mode: "run"`: `{venus_version: "1", plugin, mode, strategy, input}`. The strategy must exist, have
  `status: "validated"`, and match the plugin's name and version.
Anything else is refused by `venus.check_request` with a `VenusError` (`code`, `message`, `path`).

## Interfaces you build against (frozen; change only with the orchestrator)
- `venus.load_plugin(path) -> Plugin`, `venus.load_plugins(dir) -> {name: Plugin}`
- `Plugin`: `name, version, brief, input_schema, output_schema, seed_tendencies`, `validate_input(value, path)`,
  `validate_output(value, path, code)`, `check(input, output, expected) -> Score`, `tools(input) -> list`
- `Score(total: float in [0,1], parts: {name: float}, reasons: [str])`, `.to_dict()`
- `StrategyStore(dir).get(id) -> Strategy` (`id, plugin, plugin_version, status, base_model, tendencies,
  is_validated`)
- `check_request(raw, plugins, strategies) -> TrainingRequest(plugin, cases) | RunRequest(plugin, strategy, input)`
- `Tendency(id, text)`; errors: `VenusError` → `PluginError`, `StrategyError`, `InputError`, `ModeError`
- Run-time code lives in `venus/agent/` (phase 10): every module in `tests/test_boundary.py` `RUNTIME` plus `core`
  (`Agent`, `AgentError`). The old names (`venus.runner`, `venus.models`, ...) are 3-line stubs that alias the same
  module objects; `venus/__init__.py` loads names lazily, so `import venus.agent` never loads serve/training/FastAPI.
  `Agent(root_dir, *, model, model_factory, web_tools, cala, on_cala_result, fallback_base_model, environ)`,
  `.run(plugin_id, input_data, strategy=None, *, trace_id, on_cala_result) -> dict` (never raises for run problems),
  `.settings(plugin_id, strategy=None)`; full contract in `../plans/archive/shared_context.md` Section 4.2. Plugins load with
  `load_plugin(path, runtime_only=True)` there: no checker, no gate.
- Schemas (`venus.load_schema(name)`): `plugin`, `strategy`, `request`, `response` in `venus/agent/schemas/`.
  Responses must validate against `response.schema.json` (see `examples/response_*.json`).
- Models: `resolve_model(strategy.base_model) -> ModelSpec(provider, base_url, model, key_env, client, tool_choices)`
  (presets `nemotron`, `gemma`, `claude-research`, `claude-fast`, `meta`, `gemini`; providers `verda` default, `nvidia`,
  `anthropic` (client `AnthropicClient` in `anthropic_client.py`, same `.chat`), `meta`, `gemini`). Clients expose
  `.tool_choices`; `ModelReply.raw` holds provider-native blocks the runner replays under the assistant's `"_raw"`. `ModelClient(spec, budget=None).chat(messages, tools=None,
  tool_choice=None, max_tokens=1024, temperature=None, seed=None) -> ModelReply(text, tool_calls: [ToolCall(id, name,
  arguments: dict|None, parse_error)], usage {input_tokens, output_tokens}, model, finish_reason)`. `tool_choice`:
  `"auto" | "required" | "none" | {"name": fn}`. Tools: `function_tool(name, description, parameters)`.
- Tests use `FakeModel(script_list_or_fn, budget=None)` (same `.chat`, records `.calls`) with `fake_text(text)` and
  `fake_tool_call(name, args)`. Never construct a real `ModelClient` in tests without an `httpx.MockTransport`.
- `Budget(max_model_calls, max_input_tokens, max_output_tokens, max_seconds)`: `.check()`, `.charge(in, out)`,
  `.spent()` -> `{model_calls, input_tokens, output_tokens, seconds}`.
- Tools: `Tool(name, description, parameters, fn, web=False)`; `collect_tools(plugin, input, web_tools)` = plugin's
  tools + web tools unless `plugin.web_enabled` is false. Tool names use `[A-Za-z0-9_-]`.
- Agent loop: `run_case(plugin, input, tendencies, model, tools=(), max_turns=8, max_tokens=1024) -> RunResult(output,
  sources, warnings, usage{model_calls, input_tokens, output_tokens, web_calls, seconds}, trace, trace_id)`. With a
  web tool, turn 1 is `tool_choice="required"` where the model allows it; otherwise "auto" + an instruction, one
  reminder, then a `no forced search` warning. Without "none", the last turn and the repair go out with no tools. Final answer `{"output", "sources"}`; one repair try.
- Web: `web_tools(client=None) -> [web_search, web_scrape, web_news]` ([] without `CONTEXT_DEV_API_KEY`);
  `ContextDev(api_key, http_client=...)` with `.search/.scrape/.news`; failures raise `WebError` (shown to the agent).
- Training: `train(request, model, web_tools, strategies_dir, runs_dir, base_model) -> response dict` (research step →
  draft strategy → cases scored → `runs/<trace_id>/training.jsonl`).
- Serving: `Venus(plugins_dir, strategies_dir, runs_dir, model_factory, web_tools, env).handle(raw) -> response`;
  `create_app(venus)` (FastAPI, `POST /v1/requests`, `GET /v1/health`); `python -m venus serve|handle`.

## Error codes in use
`unknown_mode`, `version_unsupported`, `request_invalid`, `plugin_not_found`, `cases_missing`, `cases_empty`,
`expected_missing`, `expected_invalid`, `input_invalid`, `case_id_duplicate`, `strategy_not_allowed`,
`expected_not_allowed`, `strategy_missing`, `strategy_not_found`, `strategy_invalid`, `strategy_not_validated`,
`strategy_plugin_mismatch`, `plugin_manifest_missing`, `plugin_manifest_invalid`, `plugin_schema_missing`,
`plugin_schema_invalid`, `plugin_checker_missing`, `plugin_tools_missing`, `plugin_import_failed`,
`plugin_checker_failed`, `plugin_bad_score`, `plugin_tools_failed`, `plugin_duplicate`, `model_config_missing`,
`model_auth_failed`, `model_bad_request`, `model_unavailable`, `model_bad_reply`, `budget_exceeded`, `output_invalid`,
`tool_name_duplicate`, `web_failed`, `web_config_missing`, `all_cases_failed`, `request_timeout`, `storage_failed`. Add new codes;
never rename.

## Working rules
- Touch only the paths in your lane brief (`agents/lane-*.md`). Need an interface change? Ask the orchestrator.
- Work in your own git worktree and branch; the orchestrator merges.
- Python 3.12, standard library first; new dependencies only if your brief names them.
- Tests: `.venv/bin/python -m pytest -q` from this folder. Tests never call real networks or real models (use fakes
  and a local stub server on 127.0.0.1). Keep tests fast.
- No secrets in code or configs; keys come from the environment (`venus.load_env()` reads `.env`).
- Event rule: all code is written at Junction 2026; nothing copied from older projects.

## Layout
```
venus/            the core package (no task code)
  schemas/        JSON Schemas of the contract
  request.py      mode gate          runner.py   agent loop       training.py  training intake
  models.py       model client       config.py   presets          budget.py    caps
  anthropic_client.py  Anthropic Messages API client (same .chat door)
  tools.py        Tool               web.py      Context.dev      serve.py     handle + HTTP
tools/            manual scripts (models_probe.py)
plugins/          task plugins (none shipped yet)
strategies/       strategy files (<id>.json)
examples/         example requests and responses
tests/            tests + fixtures (toy plugin, strategies)
```
