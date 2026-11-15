"""Thin httpx client for the Cala API.

Every successful response is cached under data/cache/ so the demo runs offline
and gives the same results every time. Cache keys are SHA1 of method+url+body.
Errors are never cached.

Cala endpoints used (docs.cala.ai, checked 2026-11-13):
  POST /v1/knowledge/query      body {"input": q, "return_entities": true}
                                -> {"results": [row, ...], "entities": [...] | null}
  GET  /v1/entities?name=&limit= -> {"entities": [{id, name, entity_type, description}]}
  POST /v1/entities/{uuid}      optional body {"properties": [...], "relationships": {...}}
Auth: header X-API-KEY (no Bearer).
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import httpx

try:  # Dan's loader (shared_context.md 4.1). Until it lands, read the shell env only.
    from envload import load_env
except ImportError:  # pragma: no cover - removed once app/envload.py exists
    def load_env() -> dict:
        return {}

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"
DEFAULT_BASE_URL = "https://api.cala.ai"


class CalaError(RuntimeError):
    """Any Cala failure: no key, HTTP error, network error, bad JSON."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def _setting(name: str, env: dict) -> str | None:
    # Shell values win over .env values.
    return os.environ.get(name) or env.get(name) or None


class CalaClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 30.0,
        http_client: httpx.Client | None = None,
        cache_dir: Path | str | None = None,
    ):
        env = load_env() or {}
        self.api_key = api_key or _setting("CALA_API_KEY", env) or ""
        self.base_url = (base_url or _setting("CALA_BASE_URL", env) or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.http_client = http_client
        self.cache_dir = Path(cache_dir) if cache_dir else CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # -- public API --------------------------------------------------------

    def knowledge_query(self, question: str) -> dict:
        """Typed JSON rows for a natural-language question."""
        return self._request("POST", "/v1/knowledge/query", body={"input": question, "return_entities": True})

    def entity_search(self, name: str, limit: int = 20) -> dict:
        if not 1 <= len(name) <= 100:
            raise ValueError("Cala entity_search: name must be 1-100 characters")
        if not 1 <= limit <= 100:
            raise ValueError("Cala entity_search: limit must be 1-100")
        return self._request("GET", "/v1/entities", params={"name": name, "limit": limit})

    def entity(self, entity_id: str, properties: list | None = None, relationships: dict | None = None) -> dict:
        body = {}
        if properties is not None:
            body["properties"] = properties
        if relationships is not None:
            body["relationships"] = relationships
        return self._request("POST", f"/v1/entities/{entity_id}", body=body or None)

    # -- internals ---------------------------------------------------------

    def _cache_path(self, method: str, url: str, params: dict | None, body: dict | None) -> Path:
        raw = json.dumps({"m": method, "u": url, "p": params, "b": body}, sort_keys=True)
        return self.cache_dir / (hashlib.sha1(raw.encode()).hexdigest() + ".json")

    def _request(self, method: str, path: str, params: dict | None = None, body: dict | None = None) -> dict:
        url = f"{self.base_url}{path}"
        cache = self._cache_path(method, url, params, body)
        if cache.exists():
            return json.loads(cache.read_text())
        if not self.api_key:
            raise CalaError(
                f"CALA_API_KEY is not set and no cached response exists for {method} {path}. "
                "Put the key in the root .env, or use the sample dataset (see README.md)."
            )
        headers = {"X-API-KEY": self.api_key, "Accept": "application/json"}
        try:
            if self.http_client is not None:
                resp = self.http_client.request(method, url, params=params, json=body, headers=headers,
                                                timeout=self.timeout)
            else:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.request(method, url, params=params, json=body, headers=headers)
        except httpx.HTTPError as e:
            raise CalaError(f"Cala request {method} {path} failed: {type(e).__name__}: {e}") from e
        if resp.status_code >= 400:
            hint = " Check CALA_API_KEY." if resp.status_code in (401, 403) else ""
            raise CalaError(
                f"Cala {method} {path} returned HTTP {resp.status_code}: {resp.text[:200]}.{hint}",
                status=resp.status_code,
            )
        try:
            data = resp.json()
        except ValueError as e:
            raise CalaError(f"Cala {method} {path} returned non-JSON: {resp.text[:200]}") from e
        cache.write_text(json.dumps(data, indent=2, sort_keys=True))
        return data
