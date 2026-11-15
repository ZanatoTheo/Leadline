#!/usr/bin/env bash
# Key-day check: run after the root .env has real keys. Prints OK/FAIL per step and exits 1 if any step failed.
# Never prints key values. Run from anywhere:  bash scripts/live_check.sh
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_PY="$ROOT/.venv/bin/python"
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
step "3 app tests"  bash -c "cd '$ROOT/app' && '$APP_PY' -m pytest -q"

[ "$FAILED" -eq 0 ] && echo "ALL OK" || echo "SOME STEPS FAILED"
exit "$FAILED"
