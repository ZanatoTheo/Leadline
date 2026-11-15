"""Leadline profiles on the training side: build each user's profile + initial rating once with the
`leadline-profile` plugin, keep every version in SQLite, and revise on request.

- `ProfileStore(path)`: stdlib sqlite3; `put` writes a new version (1, 2, ...), `get` returns the latest or a given
  version, `history` lists them all. Each row: key, version, created_at, profile, rating, changes.
- `get_or_build(store, user, run, ...)`: returns the stored profile, calling `run` (the agent) only on a miss.
- `update_profile(store, key, update, run, ...)`: asks the agent to revise the stored profile; refuses to write when
  `update_problems` finds a change without an entry or reason (e.g. a sourced field dropped silently).
- `case_runner(model, ...)`: a `run` callable that sends one input through `run_case` (the bundled agent, via
  `engine`) and counts calls.

The team keeps real users in their own database; this cache only serves training cases. Keys default to the user
id, or "<id>@<as_of>" for time-split cases, so a profile built from older facts never mixes with a newer one.
"""
import importlib.util
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import engine

PLUGIN_DIR = Path(__file__).resolve().parent / "plugins" / "leadline-profile"


def _load_checker():
    spec = importlib.util.spec_from_file_location("leadline_profile_checker", PLUGIN_DIR / "checker.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


update_problems = _load_checker().update_problems  # one rule set for the checker and the store


class ProfileError(Exception):
    pass


class ProfileStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS profiles (
                key TEXT NOT NULL, version INTEGER NOT NULL, created_at TEXT NOT NULL,
                profile TEXT NOT NULL, rating TEXT NOT NULL, changes TEXT NOT NULL,
                PRIMARY KEY (key, version))""")

    @contextmanager
    def _connect(self):
        """A connection that commits on success, rolls back on error, and is always closed."""
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)  # explicit transactions below
        try:
            db.execute("BEGIN IMMEDIATE")  # take the write lock now, so read-then-write can't interleave
            yield db
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    def put(self, key: str, profile: dict, rating: dict, changes: list, expected_version: int | None = None) -> int:
        """Write the next version for `key` and return its number. With `expected_version` (0 = none stored yet),
        refuse with ProfileError when another writer got there first, so a change list is never based on a
        stale version."""
        with self._connect() as db:
            last = db.execute("SELECT MAX(version) FROM profiles WHERE key = ?", (key,)).fetchone()[0] or 0
            if expected_version is not None and last != expected_version:
                raise ProfileError(f"{key}: stored version is {last}, expected {expected_version}")
            db.execute("INSERT INTO profiles VALUES (?, ?, ?, ?, ?, ?)",
                       (key, last + 1, datetime.now(timezone.utc).isoformat(), json.dumps(profile),
                        json.dumps(rating), json.dumps(changes)))
        return last + 1

    def get(self, key: str, version: int | None = None) -> dict | None:
        with self._connect() as db:
            if version is None:
                row = db.execute("SELECT * FROM profiles WHERE key = ? ORDER BY version DESC LIMIT 1",
                                 (key,)).fetchone()
            else:
                row = db.execute("SELECT * FROM profiles WHERE key = ? AND version = ?", (key, version)).fetchone()
        return _record(row) if row else None

    def history(self, key: str) -> list:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM profiles WHERE key = ? ORDER BY version", (key,)).fetchall()
        return [_record(r) for r in rows]


def _record(row) -> dict:
    key, version, created_at, profile, rating, changes = row
    return {"key": key, "version": version, "created_at": created_at, "profile": json.loads(profile),
            "rating": json.loads(rating), "changes": json.loads(changes)}


class CaseRunner:
    """`run(input) -> output` through `engine.run_case`. `tools` () means no web; pass
    `leadline_agent.web.web_tools()` for real research. `calls` counts agent runs; `last` keeps the last RunResult
    (usage, warnings, sources)."""

    def __init__(self, model, plugin=None, tendencies=None, tools=(), **run_args):
        self.model = model
        self.plugin = plugin or engine.load_plugin(PLUGIN_DIR)
        self.tendencies = list(self.plugin.seed_tendencies if tendencies is None else tendencies)
        self.tools = list(tools)
        self.run_args = run_args
        self.calls = 0
        self.last = None

    def __call__(self, input: dict) -> dict:
        self.calls += 1
        self.last = engine.run_case(self.plugin, input, self.tendencies, self.model, tools=self.tools, **self.run_args)
        return self.last.output


def case_runner(model, **kwargs) -> CaseRunner:
    return CaseRunner(model, **kwargs)


def profile_key(user_id: str, as_of: str | None = None) -> str:
    return f"{user_id}@{as_of}" if as_of else user_id


def _input(user, cala_facts=None, as_of=None) -> dict:
    value = {"user": user}
    if cala_facts is not None:
        value["cala_facts"] = cala_facts
    if as_of:
        value["as_of"] = as_of
    return value


def get_or_build(store: ProfileStore, user: dict, run, cala_facts=None, as_of=None, key=None) -> dict:
    """The stored profile for this user (and as_of), building it with `run` only when none is stored."""
    key = key or profile_key(user["id"], as_of)
    hit = store.get(key)
    if hit is not None:
        return hit
    value = _input(user, cala_facts, as_of)
    output = run(value)
    problems = update_problems(value, output)
    if problems:
        raise ProfileError(f"profile for {key} not stored: " + "; ".join(problems))
    try:
        store.put(key, output["profile"], output["rating"], output["changes"], expected_version=0)
    except ProfileError:
        pass  # another writer built it meanwhile: use theirs
    return store.get(key)


def update_profile(store: ProfileStore, key: str, update: dict, run, user=None, cala_facts=None,
                   as_of=None) -> dict:
    """Revise the stored profile under `key` (`update` = {reason, new_info}); writes the next version."""
    current = store.get(key)
    if current is None:
        raise ProfileError(f"no stored profile for {key}; build it first")
    if user is None:
        user = {k: current["profile"][k] for k in ("id", "kind", "name")}
        if current["profile"].get("website"):
            user["website"] = current["profile"]["website"]
    value = _input(user, cala_facts, as_of)
    value["current"] = {"profile": current["profile"], "rating": current["rating"]}
    value["update"] = update
    output = run(value)
    problems = update_problems(value, output)
    if problems:
        raise ProfileError(f"update of {key} refused: " + "; ".join(problems))
    store.put(key, output["profile"], output["rating"], output["changes"], expected_version=current["version"])
    return store.get(key)
