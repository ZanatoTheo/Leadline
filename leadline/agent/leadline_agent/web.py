"""Built-in web tools backed by Context.dev (https://docs.context.dev): search, scrape to markdown, news.

On for every plugin unless its manifest says `"web": false`. Key from `CONTEXT_DEV_API_KEY` (or `CONTEXTDEV_API_KEY`).
Failures raise WebError; the runner hands them to the agent as readable tool errors, so a blocked site never crashes
a run."""
import os
import threading
import time

import httpx

from .cache import cache_from_env
from .errors import WebError
from .tools import Tool

BASE_URL = "https://api.context.dev/v1"
KEY_ENVS = ("CONTEXT_DEV_API_KEY", "CONTEXTDEV_API_KEY")
FRESHNESS = ["last_24_hours", "last_week", "last_month", "last_year"]
FRESH_TTL = 24 * 3600  # search and news results are reused for a day; scraped pages have no limit (fresh=True skips)
# A failed result (a client error, a scrape that returned no page) is replayed for an hour, so an immediate rerun sees
# the same tool result and pays nothing; later runs ask again. Auth errors, rate limits, server errors, timeouts and
# network errors are never stored: they say nothing about the request itself.
FAIL_TTL = 3600
NOT_STORED = {401, 403, 429}


def key_from_env(environ=None) -> str | None:
    environ = os.environ if environ is None else environ
    for name in KEY_ENVS:
        if environ.get(name):
            return environ[name]
    return None


class ContextDev:
    def __init__(self, api_key=None, base_url=BASE_URL, http_client=None, timeout: float = 45.0,
                 max_concurrent: int = 50, sleep=time.sleep, environ=None, cache=None, fresh_ttl=FRESH_TTL,
                 fail_ttl=FAIL_TTL):
        self.cache = cache  # a DiskCache, or None for no caching
        self.fresh_ttl = fresh_ttl  # search/news reuse; None = never expire (training: a rerun must replay exactly)
        self.fail_ttl = fail_ttl
        self.api_key = api_key or key_from_env(environ)
        if not self.api_key:
            raise WebError("web_config_missing", f"no Context.dev key: set {KEY_ENVS[0]}")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.sleep = sleep
        self._http = http_client or httpx.Client(timeout=timeout)
        self._slots = threading.BoundedSemaphore(max_concurrent)  # the event key allows 50 requests at once

    def _post(self, path: str, payload: dict, ttl: float | None = None, use_cache: bool = True, accept=None,
              keep_failed=None) -> dict:
        """POST with a disk cache in front. 2xx replies that `accept(data)` approves are stored under `ttl`. A client
        error, or a rejected reply that `keep_failed(data)` calls a real answer about the request (a blocked page), is
        stored apart for `fail_ttl` and replayed as is (see FAIL_TTL); other odd replies are asked again.
        `use_cache=False` skips the reads but still refreshes the entries."""
        # `maxAgeMs` only says how fresh the answer must be, so it is not part of the key: a fresh=True call then
        # replaces the entry that plain calls read.
        key_payload = {k: v for k, v in payload.items() if k != "maxAgeMs"}
        key = self.cache.key("context.dev", self.base_url, path, key_payload) if self.cache else None
        failed_key = self.cache.key("context.dev-failed", self.base_url, path, key_payload) if self.cache else None
        if key and use_cache:
            hit = self.cache.get(key, ttl=ttl)
            if hit is not None:
                return hit
            failed = self.cache.get(failed_key, ttl=self.fail_ttl)
            if isinstance(failed, dict) and isinstance(failed.get("error"), str):
                raise WebError(failed.get("code") or "web_failed", failed["error"])
            if isinstance(failed, dict) and isinstance(failed.get("data"), dict):
                return failed["data"]
        try:
            data = self._send(path, payload)
        except WebError as e:
            status = getattr(e, "status", None)
            if failed_key and status is not None and 400 <= status < 500 and status not in NOT_STORED:
                self._store(failed_key, {"error": e.message, "code": e.code})
            raise
        if key and (accept is None or accept(data)):
            self._store(key, data)
        elif failed_key and keep_failed is not None and keep_failed(data):
            self._store(failed_key, {"data": data})
        return data

    def _store(self, key, value) -> None:
        try:
            self.cache.put(key, value)
        except OSError:
            pass  # a full or read-only cache folder must not throw away a result that was already paid for

    def _send(self, path: str, payload: dict) -> dict:
        for attempt in range(2):
            try:
                with self._slots:
                    r = self._http.post(self.base_url + path, json=payload, timeout=self.timeout,
                                        headers={"Authorization": f"Bearer {self.api_key}"})
            except httpx.TimeoutException:
                raise WebError("web_failed", f"{path} timed out after {self.timeout:g}s") from None
            except httpx.HTTPError as e:
                raise WebError("web_failed", f"{path}: {type(e).__name__}: {e}") from None
            if r.status_code == 429 and attempt == 0:
                try:
                    wait = float(r.headers.get("Retry-After") or 1)
                except ValueError:
                    wait = 1.0
                self.sleep(min(wait, 5.0))
                continue
            if r.status_code >= 400:
                try:
                    err = r.json()
                except ValueError:
                    err = {}
                error = WebError("web_failed", f"{path} returned {r.status_code} {err.get('error_code', '')}: "
                                               f"{err.get('message', r.text[:200])}".strip())
                error.status = r.status_code
                raise error
            try:
                return r.json()
            except ValueError:
                raise WebError("web_failed", f"{path} returned a reply that is not JSON") from None
        raise WebError("web_failed", f"{path} is rate limited; try again later")

    def search(self, query: str, num_results: int = 5, freshness: str | None = None) -> dict:
        payload = {"query": query, "numResults": max(1, min(int(num_results), 20))}
        if freshness:
            payload["freshness"] = freshness
        data = self._post("/web/search", payload, ttl=self.fresh_ttl, accept=lambda d: isinstance(d.get("results"), list))
        return {"results": [{"url": r.get("url"), "title": r.get("title"), "description": r.get("description")}
                            for r in data.get("results", [])]}

    def scrape(self, url: str, fresh: bool = False, max_chars: int = 8000) -> dict:
        payload = {"url": url, "formats": {"markdown": True}, "sharedParams": {"mainContentOnly": True}}
        if fresh:
            payload["maxAgeMs"] = 0
        data = self._post("/web/scrape", payload, use_cache=not fresh,
                          accept=lambda d: bool((d.get("markdown") or {}).get("success")),
                          keep_failed=lambda d: isinstance(d.get("markdown"), dict)
                          and d["markdown"].get("success") is False)
        md = data.get("markdown") or {}
        if not md.get("success"):
            raise WebError("web_failed", f"scrape of {url} failed: {md.get('error_code', 'NO_MARKDOWN')}: "
                                         f"{md.get('message', 'no markdown returned')}")
        text = md.get("data") or ""
        return {"url": data.get("url", url), "title": (data.get("metadata") or {}).get("title"),
                "markdown": text[:max_chars], "truncated": len(text) > max_chars}

    def news(self, query: str, limit: int = 5) -> dict:
        payload = {"searchBy": {"type": "natural_language", "query": query}, "limit": max(1, min(int(limit), 20))}
        data = self._post("/news/search", payload, ttl=self.fresh_ttl, accept=lambda d: isinstance(d.get("data"), list))
        return {"articles": [{"url": a.get("url"), "title": a.get("title"), "description": a.get("description"),
                              "published_at": a.get("published_at"), "source": (a.get("source") or {}).get("name")}
                             for a in data.get("data", [])]}


def web_tools(client: ContextDev | None = None, environ=None, allow_fresh: bool = True) -> list:
    """The three web tools, or [] when no Context.dev key is set. `allow_fresh=False` (training) drops the scrape's
    `fresh` option and ignores it if sent, so every scrape can be replayed from the cache."""
    if client is None:
        key = key_from_env(environ)
        if not key:
            return []
        client = ContextDev(api_key=key, cache=cache_from_env(environ))
    scrape_props = {"url": {"type": "string", "description": "http(s) URL to read."}}
    if allow_fresh:
        scrape_props["fresh"] = {"type": "boolean", "description": "true = skip the cache and fetch now.",
                                 "default": False}
    return [
        Tool("web_search", "Search the web. Returns result titles, URLs and short descriptions.", {
            "type": "object", "required": ["query"], "properties": {
                "query": {"type": "string", "description": "What to search for; supports site:, quotes, OR."},
                "num_results": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
                "freshness": {"type": "string", "enum": FRESHNESS}}},
             lambda a: client.search(a["query"], a.get("num_results", 5), a.get("freshness")), web=True),
        Tool("web_scrape", "Fetch one web page as markdown text. Use it to read a result in full.", {
            "type": "object", "required": ["url"], "properties": scrape_props},
             lambda a: client.scrape(a["url"], allow_fresh and bool(a.get("fresh", False))), web=True),
        Tool("web_news", "Search recent news articles. Returns headlines, URLs, dates and matching passages.", {
            "type": "object", "required": ["query"], "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5}}},
             lambda a: client.news(a["query"], a.get("limit", 5)), web=True),
    ]
