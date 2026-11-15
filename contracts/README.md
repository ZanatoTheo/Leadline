# contracts/

JSON Schemas of the frontend's TypeScript types: the structures the Next.js server code expects from the Python
leadline service. The TS files in `frontend/` are the source of truth; these schemas are generated from them.

## Regenerate

```bash
bash scripts/gen_contract_schemas.sh   # needs network once (npx ts-json-schema-generator@2.9.0), ~2 min
```

Writes `contracts/schemas/<Type>.json` (21 types) and never writes inside `frontend/`. Never hand-edit a schema:
when a type changes in `frontend/`, regenerate, then run `cd leadline && ../.venv/bin/python -m pytest -q`.

| Source file (`frontend/src/`) | Types |
|---|---|
| `lib/leadline/types.ts` | FounderProfile, Source, Deal, FundClose, ShortlistResponse, RankedInvestor, InvestorBrief, TwinsResponse, SignalsResponse |
| `lib/leadline/match-types.ts` | FounderRecord, PublicFounder, Intro, FitReport, InvestorThesis, DiscoverResponse, CompanyDiligence, StartupDiligence |
| `lib/server/db.ts` | User, Session |
| `lib/server/auth.ts` | SessionUser |
| `lib/cala/client.ts` | CalaEntity |

## Notes

- Schemas are strict: `additionalProperties: false` and every non-optional field required. Text fields are plain
  `string` (never null), so `leadline/shapes.py` turns DB NULLs into `""` and drops internal keys (`provenance`,
  `isDemo`, `country`).
- `StartupDiligence.twins` is written as an inline `import("./types").TwinsResponse` type, which the generator cannot
  parse. The script generates that one type from a temp copy of `types.ts` + `match-types.ts` where only that
  reference is turned into a normal import; the copy is rebuilt from the real files on every run.
- `sources.json` holds the sha256 of each TS file the schemas came from; `test_schemas_are_current_for_the_frontend_sources`
  fails when one changed without regenerating (expected after edits to `lib/server/*.ts` or `lib/cala/client.ts`:
  regenerate). The script builds in a temp folder and replaces `contracts/schemas/` only when every type succeeded.
- Used by `leadline/tests/test_shapes.py` (now), the service tests and the end-to-end smoke check (later phases).
