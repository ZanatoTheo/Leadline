# Venus

A general-purpose engine that runs **behavioral tendencies** (short instructions that shape how an agent acts) for
any task defined by a **plugin**. It searches the web by default, drafts its first tendencies from that search, scores
them on validated cases, and serves a validated strategy behind one endpoint: input in, output back.

Venus holds no task code. A task is a plugin folder; the way Venus does it is a strategy file.

## Install

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt -e .
cp .env.example .env    # then fill in the keys
```

Keys (`.env`, found by walking up from the current folder, or the file named in `VENUS_ENV_FILE`):

| Variable | What for |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic (Messages API, `venus.anthropic_client`). Presets `claude-research`, `claude-fast` (both `claude-opus-5-5` unless `VENUS_CLAUDE_RESEARCH_MODEL` / `VENUS_CLAUDE_FAST_MODEL` say otherwise). Adaptive thinking with `VENUS_CLAUDE_EFFORT` (default `medium`), refusal fallback on, prompt caching on, no temperature/seed sent, `max_tokens` floor `VENUS_CLAUDE_MIN_TOKENS` (default 16000, thinking shares it), timeout 300 s unless `VENUS_MODEL_TIMEOUT`. These models refuse forced tool use, so the first web search is asked for, reminded once, then warned about. |
| `VERDA_API_KEY`, `VERDA_BASE_URL` | Default provider when a base_model names none (OpenAI-compatible endpoint) |
| `NVIDIA_API_KEY` | Fallback provider (NVIDIA Build). Venus sends at most 40 requests a minute to it (the free tier's limit) and waits for a slot instead of hitting 429s. |
| `VENUS_NEMOTRON_MODEL`, `VENUS_GEMMA_MODEL` | Model ids behind the `nemotron` and `gemma` presets |
| `META_API_KEY` (or `MODEL_API_KEY`), `VENUS_META_MODEL` | Meta Model API, preset `meta` (`muse-spark-1.3`). Accepts only `tool_choice="auto"`: no forced search, and final answers are asked for without tools. |
| `GEMINI_API_KEY`, `VENUS_GEMINI_MODEL` | Gemini through its OpenAI-style endpoint, preset `gemini`, at most 10 requests a minute. |
| `VENUS_TRAIN_MODEL`, `VENUS_TRAIN_PROVIDER` | Model for training requests: `VENUS_TRAIN_MODEL`, else the provider's default preset (`anthropic` -> `claude-research`, `meta` -> `meta`, `gemini` -> `gemini`), else `nemotron` |
| `VENUS_CACHE_DIR` | Folder for the web-call cache (default `.venus_cache` in the current folder; `off` turns it off). Search and news results are reused for 24 h; `web_scrape` with `fresh: true` skips it. Only successful replies are stored. |
| `VENUS_MODEL_CACHE` | `1` caches model replies in a `models` folder inside the cache folder (off by default). Used only for repeatable requests: with a `seed`, or temperature 0. If the caller gives neither, Venus asks for temperature 0. A hit makes no call and shows in `usage.cache_hits`. Trade-offs: turning it on changes sampling for calls that set neither value; a seeded reply at temperature > 0 is reused even though providers do not promise the same reply for the same seed; an answer that fails validation is dropped from the cache. |
| `VENUS_MODEL_TIMEOUT` | Seconds to wait for one model call (default 60, which is Verda's cut-off). Retries stop when the request budget's seconds cap is spent. |
| `CONTEXT_DEV_API_KEY` | Built-in web tools (search, scrape, news) |

Check the model endpoints once keys are in: `.venv/bin/python tools/models_probe.py`.

## Two kinds of request

Every request is one of these. Anything else is refused with an error code.

**Training**: validated cases, each with the `expected` output to compare against.
```json
{"venus_version": "1", "plugin": "toy-sentiment", "mode": "training",
 "cases": [{"id": "c1", "input": {"text": "I love this"}, "expected": {"label": "positive"}}]}
```
Venus researches the task on the web, drafts tendencies (each citing its URLs), saves them as a **draft** strategy in
`strategies/`, runs every case with them, and returns per-case outputs and scores. Records go to
`runs/<trace_id>/training.jsonl`.

**Run**: one input and a strategy whose `status` is `validated`.
```json
{"venus_version": "1", "plugin": "toy-sentiment", "mode": "run", "strategy": "toy-validated",
 "input": {"text": "This is not good"}}
```

Responses follow `venus/agent/schemas/response.schema.json`: `status` (`ok` | `partial` | `error`), `outputs`
(with `sources`), `scores` (training only), `usage` (model calls, tokens, web calls, seconds), `warnings`, `error`.
See `examples/response_*.json`.

## Use it

From Python:
```python
from venus import Venus
venus = Venus(plugins_dir="plugins", strategies_dir="strategies", runs_dir="runs")
response = venus.handle(request_dict)
```

Over HTTP:
```bash
.venv/bin/python -m venus serve --port 8000
curl -s localhost:8000/v1/requests -H 'content-type: application/json' -d @examples/request_run.json
curl -s localhost:8000/v1/health
```
Refusals come back as the same response shape with `status: "error"`: HTTP 400 for bad requests, 404 for an
unknown plugin or strategy, 5xx when the model side fails.

One request from the shell: `.venv/bin/python -m venus handle request.json`.

Working example (offline, no keys): `.venv/bin/python examples/use_venus.py`; add `--live` for real models.

## Run the standalone agent (run mode only)

`venus.agent` is the part of Venus that ships: plugins + validated strategies, no training, no server, no FastAPI.

```python
from venus.agent import Agent          # exported copy: from leadline_agent import Agent

agent = Agent("path/with/plugins-and-strategies")
resp = agent.run("my-plugin", {"text": "..."})               # strategy defaults to "my-plugin-default"
if resp["status"] == "ok":
    output = resp["outputs"][0]["output"]
else:
    print(resp["error"]["code"], resp["error"]["message"])   # run() never raises for run problems
```

On `verda`/`nvidia` a run asks for `VENUS_MAX_TOKENS` (default 8192, at most 32768) so reasoning leaves room for the
answer; Verda clients wait at least 120 s. `VENUS_FALLBACK_PROVIDER=nvidia` (+ `VENUS_FALLBACK_MODEL`) retries a run
once on NVIDIA when the primary model is down, times out or is misconfigured.

Export it as a folder that runs without Venus (no `venus` import, `python -I` safe):

```bash
python -m venus export --plugins leadline-profile,leadline-match --strategies ../leadline/strategies \
    --out ../dist/leadline-agent        # exit 2 = refused (draft or missing strategy, non-empty target, ...)
```

It writes `leadline_agent/` (this package), `plugins/` without checkers or `gate.py`, the `<plugin>-default`
strategies (validated only; `base_model` switched to Verda Nemotron unless `--keep-base-model`), `requirements.txt`,
`README.md` and `export.json`.

## Write a plugin

See `plugins/README.md`. A plugin is `plugin.json` + input and output JSON Schemas + a checker
`check(input, output, expected) -> {total, parts, reasons}` (total in [0, 1]) + optional tools. Web tools are on;
`"web": false` turns them off.

## Write a strategy

`strategies/<id>.json` (schema: `venus/agent/schemas/strategy.schema.json`):
```json
{"id": "toy-validated", "plugin": "toy-sentiment", "plugin_version": "1.0.0", "status": "validated",
 "base_model": {"model": "nemotron"},
 "tendencies": [{"id": "t-negation", "text": "Treat 'not' before a positive word as negative."}],
 "created_at": "2026-11-13T22:00:00Z"}
```
`base_model.model` is a preset (`nemotron`, `gemma`, `claude-research`, `claude-fast`, `meta`, `gemini`) or a raw model id; `provider` is `verda` (default), `nvidia`, `anthropic`, `meta` or `gemini`. A preset tied to a provider (the Claude, Meta and Gemini ones) uses it unless `provider` is given.
Training writes `draft` strategies. Review one, then set `status` to `validated` to serve it.

## Tests

`.venv/bin/python -m pytest -q` runs in a few seconds. No network and no real models are used (`FakeModel`,
`httpx.MockTransport`).

The full pipeline map (stages, settings, error codes): see `AGENTS.md` and the published pipeline page.
