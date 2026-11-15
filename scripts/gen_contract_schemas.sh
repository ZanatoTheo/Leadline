#!/usr/bin/env bash
# Generate JSON Schemas from the frontend's TypeScript types (the contract the Python service must match).
# Writes contracts/schemas/<Type>.json plus contracts/schemas/sources.json (sha256 of each TS file read, so tests can
# tell when a type changed without regenerating). Builds in a temp folder and replaces contracts/schemas/ only when
# every type succeeded: a failed run leaves the old schemas untouched. Never writes inside frontend/.
# Needs network once for npx. Usage: bash scripts/gen_contract_schemas.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FINAL="$ROOT/contracts/schemas"
GEN="ts-json-schema-generator@2.9.0"
SRC="$ROOT/frontend/src"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
OUT="$TMP/schemas"
mkdir -p "$OUT" "$TMP/errors"

# file (relative to frontend/src) : type names
TYPES=(
  "lib/leadline/types.ts:FounderProfile Source Deal FundClose ShortlistResponse ShortlistPending RankedInvestor InvestorBrief TwinsResponse SignalsResponse"
  "lib/leadline/match-types.ts:FounderRecord PublicFounder Intro FitReport InvestorThesis DiscoverResponse CompanyDiligence"
  "lib/server/db.ts:User Session"
  "lib/server/auth.ts:SessionUser"
  "lib/cala/client.ts:CalaEntity"
)

failed=0
count=0

generate() {  # tsconfig path type
  local tsconfig="$1" path="$2" type="$3"
  if npx --yes "$GEN" --tsconfig "$tsconfig" --path "$path" --type "$type" \
      --no-type-check --expose export -o "$OUT/$type.json" >/dev/null 2>"$TMP/errors/$type.err"; then
    count=$((count + 1))
  else
    echo "FAILED: $type ($path):" >&2
    cat "$TMP/errors/$type.err" >&2
    failed=$((failed + 1))
  fi
}

for entry in "${TYPES[@]}"; do
  file="${entry%%:*}"
  for type in ${entry#*:}; do
    generate "$ROOT/frontend/tsconfig.json" "$SRC/$file" "$type"
  done
done

# StartupDiligence.twins is written as an inline `import("./types").TwinsResponse` type, which the generator cannot
# parse. Generate it from a temp copy of types.ts + match-types.ts where only that reference becomes a normal import.
# The copy is rebuilt from the real files on every run, so it cannot drift.
COPY="$TMP/sd"
mkdir -p "$COPY"
cp "$SRC/lib/leadline/types.ts" "$SRC/lib/leadline/match-types.ts" "$COPY/"
sed -i 's/import("\.\/types")\.TwinsResponse/TwinsResponse/' "$COPY/match-types.ts"
sed -i '1i import type { TwinsResponse } from "./types";' "$COPY/match-types.ts"
printf '{"compilerOptions":{"strict":true,"target":"ES2022","module":"ESNext","moduleResolution":"Bundler"}}' \
  > "$COPY/tsconfig.json"
generate "$COPY/tsconfig.json" "$COPY/match-types.ts" StartupDiligence

if [ "$failed" -ne 0 ]; then
  echo "failed: $failed type(s); contracts/schemas/ left unchanged" >&2
  exit 1
fi

# sources.json: the TS files the schemas were generated from (paths relative to the repo) and their sha256.
(
  cd "$ROOT"
  printf '{\n'
  first=1
  for entry in "${TYPES[@]}"; do
    rel="frontend/src/${entry%%:*}"
    [ "$first" -eq 1 ] || printf ',\n'
    printf '  "%s": "%s"' "$rel" "$(sha256sum "$rel" | cut -d' ' -f1)"
    first=0
  done
  printf '\n}\n'
) > "$OUT/sources.json"

rm -rf "$FINAL"
mkdir -p "$(dirname "$FINAL")"
mv "$OUT" "$FINAL"
echo "wrote $count schemas to ${FINAL#$ROOT/}"
