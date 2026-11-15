# leadline_agent: standalone run-only agent

Exported by `python -m venus export` on 2026-11-14T16:42:56+00:00 (venus_version 1).
Plugins: `leadline-profile`, `leadline-match`. Run mode only: no training, no server, no FastAPI.

## Install and run

```bash
pip install -r requirements.txt
```

```python
import sys
sys.path.insert(0, "/path/to/this/folder")
from leadline_agent import Agent, AgentError

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

This folder ships the `anthropic` client for the fallback: set `VENUS_FALLBACK_PROVIDER=anthropic` (and its key) to retry once on `anthropic` when the primary model fails.

## Strategies

Exported strategies run on {"model": "nemotron", "provider": "verda"}. Their scores were measured on the trained model; on the target model they are unmeasured. They were trained and validated on:

| Strategy | Trained base model |
|---|---|
| `leadline-profile-default` | `{"model": "claude-research", "provider": "anthropic"}` |
| `leadline-match-default` | `{"model": "claude-research", "provider": "anthropic"}` |

A strategy validated on one model is not automatically as good on another: check the scores on the new model before
relying on them.
