#!/usr/bin/env bash
# Export the trained Leadline agent (Verda Nemotron, Claude fallback) and inject it into leadline/agent/.
#   1. python -m venus export -> dist/leadline-agent/ (validated strategies only; refuses drafts)
#   2. replace leadline/agent/ with a copy (no __pycache__)
#   3. check: `python -I` imports leadline_agent from leadline/agent/ with no venus/fastapi/uvicorn loaded
# Usage: bash scripts/inject_agent.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/venus/.venv/bin/python"
DIST="$ROOT/dist/leadline-agent"
TARGET="$ROOT/leadline/agent"

(cd "$ROOT/venus" && "$PY" -m venus export --plugins leadline-profile,leadline-match \
  --strategies "$ROOT/leadline/strategies" --out "$DIST" --fallback-provider anthropic >/dev/null)

rm -rf "$TARGET"
cp -r "$DIST" "$TARGET"
find "$TARGET" -name __pycache__ -type d -prune -exec rm -rf {} +

# Leadline-only patch, reapplied on every export: model_bad_reply and output_invalid also fall back once.
"$PY" "$ROOT/scripts/patch_agent_fallback.py" "$TARGET"

"$PY" -I -c '
import json, sys
sys.path.insert(0, sys.argv[1])
import leadline_agent
from leadline_agent import Agent, AgentError
loaded = [m for m in ("venus", "fastapi", "uvicorn") if m in sys.modules]
assert not loaded, f"exported agent loaded {loaded}"
agent = Agent(sys.argv[1], web_tools=[], cala=False, environ={})
manifest = json.load(open(sys.argv[1] + "/export.json"))
print(f"injected {sys.argv[1]}: strategies {manifest['"'"'strategies'"'"']}, fallback {manifest['"'"'fallback_provider'"'"']}, "
      f"match settings keys {sorted(agent.settings('"'"'leadline-match'"'"'))}")
' "$TARGET"
