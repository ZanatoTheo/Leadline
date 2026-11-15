"""Built-in Cala tools (https://docs.cala.ai): knowledge query, knowledge search, entity search, entity get.

Run mode only. Every tool is `run_only`, so `collect_tools(mode="train")` drops it: Cala holds the facts that
training cases are scored against, and a training agent that could look them up would learn nothing. A plugin opts
in with `"cala": true` in its manifest (off by default).

Cache: one file per reply, named by sha1 of {"m","u","p","b"} (method, url, params, body), the raw JSON reply as the
body. This is the same format as app/ingest/cala_client.py, so both read each other's entries. Client errors are
kept apart for an hour (FAIL_TTL); other errors never. A cache hit needs no key and costs nothing.

Budget: `max_calls` network calls per client (cache hits are free). Serve builds a new client for each run, so the
cap is per run. Default from `VENUS_CALA_MAX_CALLS`, else 3: every call spends Cala credits.

`on_result(kind, request, reply)` is called after every reply (hit or miss), so a caller can store what the agent
saw (Leadline: leadline/db.py). A hook failure never loses the reply; the tool result gets a warning instead."""
import hashlib
import json
import os
import re
import tempfile
import time
from pathlib import Path

import httpx

from .errors import CalaError
from .tools import Tool

BASE_URL = "https://api.cala.ai"
DEFAULT_MAX_CALLS = 3
DEFAULT_CACHE_DIR = Path(".venus_cache") / "cala"
MAX_ROWS = 50
MAX_SOURCES = 20
MAX_EXCERPT = 500
# A client error (404, 400, ...) is kept for an hour in <cache_dir>/failed/, so an immediate rerun gets the same tool
# error without a call; the app client never looks there. Auth errors, rate limits, server and network errors are
# never kept: they say nothing about the request.
FAIL_TTL = 3600
NOT_STORED = {401, 403, 429}
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def _max_calls(value, environ) -> int:
    if value is None:
        value = environ.get("VENUS_CALA_MAX_CALLS") or DEFAULT_MAX_CALLS
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise CalaError("cala_config_invalid", f"VENUS_CALA_MAX_CALLS must be a whole number, got {value!r}") from None
    if value < 0:
        raise CalaError("cala_config_invalid", "VENUS_CALA_MAX_CALLS must be 0 or more")
    return value


class Cala:
    def __init__(self, api_key=None, base_url=None, http_client=None, cache_dir=None, max_calls=None,
                 environ=None, on_result=None, timeout: float = 30.0, ttl: float | None = None):
        environ = os.environ if environ is None else environ
        self.api_key = api_key or environ.get("CALA_API_KEY") or None
        self.base_url = (base_url or environ.get("CALA_BASE_URL") or BASE_URL).rstrip("/")
        self.cache_dir = Path(cache_dir or environ.get("VENUS_CALA_CACHE_DIR") or DEFAULT_CACHE_DIR)
        self.max_calls = _max_calls(max_calls, environ)
        self.on_result = on_result
        self.timeout = timeout
        self.ttl = ttl  # seconds, by file age; None = cached replies never expire
        self._http = http_client
        self.calls = 0  # network calls made (cache hits are not counted)
        self.hook_error = None  # the last on_result failure, as text

    # -- public API --------------------------------------------------------------------------------------------

    def knowledge_query(self, question: str) -> dict:
        """Typed rows for a natural-language question: {results: [row], entities: [...]}."""
        question = self._text(question, "question")
        return self._request("knowledge_query", "POST", "/v1/knowledge/query",
                             body={"input": question, "return_entities": True}, hook_request={"input": question})

    def knowledge_search(self, question: str) -> dict:
        """Claims with their sources: {explainability: [...], context: [{id, content, origins}]}."""
        question = self._text(question, "question")
        return self._request("knowledge_search", "POST", "/v1/knowledge/search", body={"input": question},
                             hook_request={"input": question})

    def entity_search(self, name: str, limit: int = 20, entity_types: list | None = None) -> dict:
        if not isinstance(name, str) or not 1 <= len(name) <= 100:
            raise CalaError("cala_bad_argument", "entity search: name must be 1-100 characters")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise CalaError("cala_bad_argument", "entity search: limit must be a whole number from 1 to 100")
        params = {"name": name, "limit": limit}
        if entity_types:
            if not all(isinstance(t, str) and t for t in entity_types):
                raise CalaError("cala_bad_argument", "entity search: entity_types must be a list of names")
            params["entity_types"] = list(entity_types)
        return self._request("entity_search", "GET", "/v1/entities", params=params, hook_request=dict(params))

    def entity_get(self, entity_id: str) -> dict:
        if not isinstance(entity_id, str) or not UUID_RE.match(entity_id):
            raise CalaError("cala_bad_argument", f"entity id must be a Cala UUID, got {entity_id!r}")
        return self._request("entity_get", "POST", f"/v1/entities/{entity_id}", hook_request={"id": entity_id})

    # -- internals ---------------------------------------------------------------------------------------------

    @staticmethod
    def _text(value, what) -> str:
        """Checked, but sent (and keyed) as given, like app/ingest/cala_client.py, so both share cache entries."""
        if not isinstance(value, str) or not value.strip():
            raise CalaError("cala_bad_argument", f"{what} must be non-empty text")
        return value

    def cache_path(self, method: str, url: str, params: dict | None, body: dict | None) -> Path:
        """Same key as app/ingest/cala_client.py CalaClient._cache_path."""
        raw = json.dumps({"m": method, "u": url, "p": params, "b": body}, sort_keys=True)
        return self.cache_dir / (hashlib.sha1(raw.encode()).hexdigest() + ".json")

    def _read_cache(self, path: Path, ttl=None):
        ttl = self.ttl if ttl is None else ttl
        try:
            if ttl is not None and time.time() - path.stat().st_mtime > ttl:
                return None
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None  # a missing or damaged entry is a miss
        return data if isinstance(data, dict) else None

    def _write_cache(self, path: Path, data) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, temp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, sort_keys=True)
            os.chmod(temp, 0o644)  # mkstemp makes 0600; other readers of the shared cache need read access
            os.replace(temp, path)
        except OSError:
            pass  # a read-only cache folder must not throw away a reply that was already paid for

    def _request(self, kind, method, path, params=None, body=None, hook_request=None) -> dict:
        url = self.base_url + path
        cache = self.cache_path(method, url, params, body)
        failed = cache.parent / "failed" / cache.name
        data = self._read_cache(cache)
        if data is None:
            stored = self._read_cache(failed, ttl=FAIL_TTL)
            if stored is not None and isinstance(stored.get("error"), str):
                raise CalaError(stored.get("code") or "cala_failed", stored["error"])
            try:
                data = self._send(method, url, path, params, body)
            except CalaError as e:
                status = getattr(e, "status", None)
                if status is not None and 400 <= status < 500 and status not in NOT_STORED:
                    self._write_cache(failed, {"error": e.message, "code": e.code})
                raise
            self._write_cache(cache, data)
            # The same key order a later cache hit reads back (the file is written sorted): the tool result text
            # then matches between a run and its rerun, so a caching model replays instead of asking again.
            data = json.loads(json.dumps(data, sort_keys=True))
        self._notify(kind, hook_request, data)
        return data

    def _send(self, method, url, path, params, body):
        if not self.api_key:
            raise CalaError("cala_config_missing", f"no cached reply for {method} {path} and CALA_API_KEY is not set")
        if self.calls >= self.max_calls:
            raise CalaError("cala_budget", f"Cala call limit reached ({self.max_calls} per run); "
                                           "answer with what you have")
        self.calls += 1
        headers = {"X-API-KEY": self.api_key, "Accept": "application/json"}
        try:
            if self._http is not None:
                resp = self._http.request(method, url, params=params, json=body, headers=headers,
                                          timeout=self.timeout)
            else:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.request(method, url, params=params, json=body, headers=headers)
        except httpx.HTTPError as e:
            raise CalaError("cala_failed", f"{method} {path}: {type(e).__name__}: {e}") from None
        if resp.status_code >= 400:
            hint = " Check CALA_API_KEY." if resp.status_code in (401, 403) else ""
            error = CalaError("cala_failed", f"{method} {path} returned HTTP {resp.status_code}: "
                                             f"{resp.text[:200]}.{hint}")
            error.status = resp.status_code
            raise error
        try:
            data = resp.json()
        except ValueError:
            raise CalaError("cala_failed", f"{method} {path} returned non-JSON: {resp.text[:200]}") from None
        if not isinstance(data, dict):
            raise CalaError("cala_failed", f"{method} {path} returned {type(data).__name__}, not an object")
        return data

    def _notify(self, kind, request, data) -> None:
        self.hook_error = None
        if self.on_result is None:
            return
        try:
            self.on_result(kind, request, data)
        except Exception as e:  # storing is a side effect; the agent still gets the reply
            self.hook_error = f"{type(e).__name__}: {e}"


# --- tools -------------------------------------------------------------------------------------------------------

def _entities(items) -> list:
    out = []
    for e in (items or [])[:MAX_ROWS]:
        if isinstance(e, dict):
            out.append({k: e.get(k) for k in ("id", "name", "entity_type") if k in e})
    return out


def trim_query(reply: dict) -> dict:
    rows = reply.get("results") or []
    rows = rows if isinstance(rows, list) else []
    return {"results": rows[:MAX_ROWS], "rows_total": len(rows), "truncated": len(rows) > MAX_ROWS,
            "entities": _entities(reply.get("entities"))}


def _origin(o) -> dict:
    o = o if isinstance(o, dict) else {}
    source = o.get("source") if isinstance(o.get("source"), dict) else {}
    doc = o.get("document") if isinstance(o.get("document"), dict) else {}
    return {"publisher": source.get("name"), "title": doc.get("name"), "url": doc.get("url") or source.get("url")}


def trim_search(reply: dict) -> dict:
    claims = [{"text": c.get("content"), "references": list(c.get("references") or [])}
              for c in (reply.get("explainability") or [])[:MAX_SOURCES] if isinstance(c, dict)]
    sources = [{"id": c.get("id"), "excerpt": str(c.get("content") or "")[:MAX_EXCERPT],
                "origins": [_origin(o) for o in (c.get("origins") or [])][:5]}
               for c in (reply.get("context") or [])[:MAX_SOURCES] if isinstance(c, dict)]
    return {"claims": claims, "sources": sources}


def trim_entity_search(reply: dict) -> dict:
    items = reply.get("entities") or []
    return {"entities": [{k: e.get(k) for k in ("id", "name", "entity_type", "description") if k in e}
                         for e in items[:MAX_ROWS] if isinstance(e, dict)]}


def _with_warning(client: Cala, result: dict) -> dict:
    if client.hook_error:
        result = {**result, "warning": f"result not saved: {client.hook_error}"}
    return result


def cala_tools(client: Cala | None = None, environ=None) -> list:
    """The four Cala tools on one client (built from the environment when not given). Build a new list per run."""
    client = client or Cala(environ=environ)
    text = {"type": "object", "properties": {"question": {"type": "string", "description": "A plain-language "
            "question, e.g. 'seed rounds of Finnish climate startups in 2024 with lead investors'."}},
            "required": ["question"]}
    return [
        Tool("cala_knowledge_query",
             "Ask Cala's company and funding database a question; get typed rows (companies, rounds, amounts, "
             "dates, investors) and the entities they mention. Cached; each new question spends one Cala call.",
             text, lambda a: _with_warning(client, trim_query(client.knowledge_query(a.get("question")))),
             run_only=True),
        Tool("cala_knowledge_search",
             "Ask Cala a question; get short claims with their sources (publisher, title, URL). Use it to cite "
             "where a fact comes from.",
             text, lambda a: _with_warning(client, trim_search(client.knowledge_search(a.get("question")))),
             run_only=True),
        Tool("cala_entity_search",
             "Find Cala entities (companies, investors, people) by name; returns ids for cala_entity_get.",
             {"type": "object", "properties": {
                 "name": {"type": "string"},
                 "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                 "entity_types": {"type": "array", "items": {"type": "string"},
                                  "description": "e.g. ['Company', 'Organization']"}},
              "required": ["name"]},
             lambda a: _with_warning(client, trim_entity_search(client.entity_search(
                 a.get("name"), limit=a.get("limit", 20), entity_types=a.get("entity_types")))),
             run_only=True),
        Tool("cala_entity_get",
             "Get one Cala entity by its UUID: description, properties and relationships.",
             {"type": "object", "properties": {"entity_id": {"type": "string"}}, "required": ["entity_id"]},
             lambda a: _with_warning(client, client.entity_get(a.get("entity_id"))),
             run_only=True),
    ]


def cala_configured(environ=None) -> bool:
    environ = os.environ if environ is None else environ
    return bool(environ.get("CALA_API_KEY"))
