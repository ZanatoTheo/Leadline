#!/usr/bin/env bash
# Key-day check: run after the root .env has real keys. Prints OK/FAIL per step and exits 1 if any step failed.
# Never prints key values. Run from anywhere:  bash scripts/live_check.sh
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_PY="$ROOT/app/.venv/bin/python"
VENUS_PY="$ROOT/venus/.venv/bin/python"
PORT="${LIVE_CHECK_PORT:-8767}"
FAILED=0

step() {  # step "name" command...
  local name="$1"; shift
  if out="$("$@" 2>&1)"; then
    echo "OK   $name"
  else
    echo "FAIL $name"; echo "$out" | tail -15 | sed 's/^/     /'; FAILED=1
  fi
}

# Load the root .env into this shell without echoing it (shell values already set win).
if [ -f "$ROOT/.env" ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in ''|\#*) continue ;; esac
    line="${line#export }"; key="${line%%=*}"; val="${line#*=}"
    val="${val%\"}"; val="${val#\"}"; val="${val%\'}"; val="${val#\'}"
    [ -n "$key" ] && [ -z "${!key+x}" ] && export "$key=$val"
  done < "$ROOT/.env"
  echo "OK   .env found (keys not shown)"
else
  echo "FAIL .env missing at $ROOT/.env (copy .env.example and fill it)"; FAILED=1
fi
for k in CALA_API_KEY CONTEXT_DEV_API_KEY CONTEXTDEV_API_KEY VERDA_API_KEY NVIDIA_API_KEY; do
  [ -n "${!k:-}" ] && echo "     $k: set" || echo "     $k: not set"
done

cd "$ROOT/app" || exit 1
step "1 ingestion from Cala (--strict, no sample fallback)" "$APP_PY" -m ingest.build_dataset --strict
step "2 Cala shape check (rows, lead mention)"              "$APP_PY" -m ingest.check_live
cd "$ROOT/venus" || exit 1
step "3 model probe (needs at least one OK line, no FAIL)"  bash -c "out=\$('$VENUS_PY' tools/models_probe.py 2>&1); rc=\$?; echo \"\$out\"; [ \$rc -eq 0 ] && echo \"\$out\" | grep -q '^OK ' && ! echo \"\$out\" | grep -q '^FAIL '"

# 4-5: start the app in live mode, hit /health and one match.
cd "$ROOT/app" || exit 1
VENUS_MODE=live "$APP_PY" -m uvicorn api.main:app --port "$PORT" >/dev/null 2>&1 &
SERVER=$!
trap 'kill "$SERVER" 2>/dev/null' EXIT
for _ in 1 2 3 4 5 6 7 8 9 10; do curl -sf "localhost:$PORT/health" >/dev/null 2>&1 && break; sleep 1; done
step "4 /health (dataset_source should be cala)" bash -c "curl -sf localhost:$PORT/health | tee /dev/stderr | grep -q '\"dataset_source\":\"cala\"'"
SUBJECT="$("$APP_PY" -c "import json;d=json.load(open('data/dataset.json'));print(d['companies'][0]['id'])" 2>/dev/null)"
step "5 live POST /api/match (source must be live)" bash -c "curl -sf -X POST localhost:$PORT/api/match -H 'content-type: application/json' -d '{\"direction\":\"startup_to_investors\",\"subject_id\":\"$SUBJECT\",\"top_k\":3}' | grep -q '\"source\":\"live\"'"
kill "$SERVER" 2>/dev/null; trap - EXIT

step "6 app tests"  bash -c "cd '$ROOT/app' && '$APP_PY' -m pytest -q"
step "7 venus tests" bash -c "cd '$ROOT/venus' && '$VENUS_PY' -m pytest -q"
if [ -d "$ROOT/cala-leads/plugin" ]; then
  step "8 cala-leads tests" bash -c "cd '$ROOT/cala-leads' && '$VENUS_PY' -m pytest -q tests"
else
  echo "FAIL 8 cala-leads tests: cala-leads/plugin missing (T6)"; FAILED=1
fi

[ "$FAILED" -eq 0 ] && echo "ALL OK" || echo "SOME STEPS FAILED"
exit "$FAILED"
