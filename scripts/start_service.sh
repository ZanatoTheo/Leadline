#!/bin/sh
# Railway start command (railway.json): seed the database on the /data volume on first start, then serve on
# 0.0.0.0:$PORT. Set LEADLINE_SERVICE_TOKEN: every route but /healthz then needs the bearer token.
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# Venus is in the repo, not pip-installed (pip runs before the repo is copied in): import it from venus/.
export PYTHONPATH="$ROOT/venus${PYTHONPATH:+:$PYTHONPATH}"
DB="${LEADLINE_DB:-/data/leadline.db}"
if [ ! -f "$DB" ]; then
  mkdir -p "$(dirname "$DB")"
  cp leadline/data/leadline.db "$DB"
  echo "seeded $DB from the repo snapshot"
fi
exec python leadline/serve.py --db "$DB" --host 0.0.0.0 --port "${PORT:-8765}"
