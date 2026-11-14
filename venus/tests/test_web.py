import json

import httpx
import pytest

from venus.fake import FakeModel, fake_text, fake_tool_call
from venus.plugin import load_plugin
from venus.runner import run_case
from venus.tools import Tool, collect_tools
from venus.web import ContextDev, WebError, key_from_env, web_tools


class Api:
    """Scripted Context.dev: each request gets the next response (status, body) or exception."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        status, body = item
        return httpx.Response(status, json=body, headers={"Retry-After": "2"} if status == 429 else {})


def client(api, sleeps=None):
    return ContextDev(api_key="ctx-test", http_client=httpx.Client(transport=httpx.MockTransport(api)),
                      sleep=(sleeps.append if sleeps is not None else lambda s: None))


def body(api, i=0):
    return json.loads(api.requests[i].content)


SEARCH_OK = (200, {"results": [{"url": "https://a.example/x", "title": "A", "description": "about a",
                                "relevance": "high", "markdown": None, "highlights": None}],
                   "query": "q", "cache_metadata": {"status": "miss", "age_ms": 0}, "request_id": "r1"})


def test_search_request_and_result():
    api = Api(SEARCH_OK)
    out = client(api).search("seed investors finland", num_results=3, freshness="last_month")
    req = api.requests[0]
    assert str(req.url) == "https://api.context.dev/v1/web/search"
    assert req.headers["Authorization"] == "Bearer ctx-test"
    assert body(api) == {"query": "seed investors finland", "numResults": 3, "freshness": "last_month"}
    assert out == {"results": [{"url": "https://a.example/x", "title": "A", "description": "about a"}]}


def test_scrape_fresh_markdown():
    api = Api((200, {"url": "https://a.example/x", "metadata": {"title": "A page"},
                     "markdown": {"requested": True, "success": True, "data": "# Hello\n" + "x" * 50}}))
    out = client(api).scrape("https://a.example/x", fresh=True, max_chars=20)
    sent = body(api)
    assert str(api.requests[0].url).endswith("/web/scrape")
    assert sent["maxAgeMs"] == 0 and sent["formats"] == {"markdown": True}
    assert out["url"] == "https://a.example/x" and out["title"] == "A page"
    assert out["markdown"].startswith("# Hello") and out["truncated"] is True and len(out["markdown"]) == 20


def test_scrape_failed_output_with_http_200():
    api = Api((200, {"url": "https://b.example", "markdown": {"requested": True, "success": False, "data": None,
                                                               "error_code": "WEBSITE_BLOCKED", "message": "blocked"}}))
    with pytest.raises(WebError) as e:
        client(api).scrape("https://b.example")
    assert "WEBSITE_BLOCKED" in e.value.message


def test_news_request_and_result():
    api = Api((200, {"data": [{"id": "1", "url": "https://n.example/1", "title": "Startup raises",
                               "description": "passage", "published_at": "2026-11-01T00:00:00Z",
                               "source": {"name": "N", "domain": "n.example", "direct": True}}],
                     "has_more": False, "next_cursor": None, "meta": {"count": 1}, "request_id": "r"}))
    out = client(api).news("nordic seed rounds", limit=4)
    assert str(api.requests[0].url).endswith("/news/search")
    assert body(api) == {"searchBy": {"type": "natural_language", "query": "nordic seed rounds"}, "limit": 4}
    assert out["articles"][0] == {"url": "https://n.example/1", "title": "Startup raises", "description": "passage",
                                  "published_at": "2026-11-01T00:00:00Z", "source": "N"}


def test_http_error_is_readable():
    api = Api((401, {"message": "bad key", "error_code": "UNAUTHORIZED", "request_id": "r"}))
    with pytest.raises(WebError) as e:
        client(api).search("q")
    assert "401" in e.value.message and "UNAUTHORIZED" in e.value.message


def test_timeout_is_readable():
    api = Api(httpx.ReadTimeout("slow"))
    with pytest.raises(WebError) as e:
        client(api).search("q")
    assert "timed out" in e.value.message


def test_rate_limit_retried_once():
    sleeps = []
    api = Api((429, {"message": "busy", "error_code": "RATE_LIMITED", "request_id": "r"}), SEARCH_OK)
    assert client(api, sleeps).search("q")["results"]
    assert sleeps == [2.0]


def test_key_from_env_accepts_both_names():
    assert key_from_env({"CONTEXT_DEV_API_KEY": "a"}) == "a"
    assert key_from_env({"CONTEXTDEV_API_KEY": "b"}) == "b"
    assert key_from_env({}) is None


def test_web_tools_shape_and_call():
    api = Api(SEARCH_OK)
    tools = web_tools(client(api))
    assert [t.name for t in tools] == ["web_search", "web_scrape", "web_news"]
    assert all(t.web for t in tools)
    assert tools[0].fn({"query": "q"})["results"][0]["url"] == "https://a.example/x"


def test_web_tools_empty_without_key():
    assert web_tools(environ={}) == []


def test_plugin_web_flag(plugin_copy, toy_plugin_dir):
    assert load_plugin(toy_plugin_dir).web_enabled is True
    assert load_plugin(plugin_copy(web=False)).web_enabled is False


def test_collect_tools_respects_web_flag(plugin_copy, toy_plugin_dir):
    web = [Tool("web_search", "s", {"type": "object"}, lambda a: {}, web=True)]
    assert [t.name for t in collect_tools(load_plugin(toy_plugin_dir), {"text": "x"}, web)] == ["web_search"]
    assert collect_tools(load_plugin(plugin_copy(web=False)), {"text": "x"}, web) == []


def test_run_case_with_web_tools_end_to_end(toy_plugin_dir):
    plugin = load_plugin(toy_plugin_dir)
    api = Api(SEARCH_OK)
    model = FakeModel([fake_tool_call("web_search", {"query": "sentiment of great"}),
                       fake_text(json.dumps({"output": {"label": "positive"}, "sources": ["https://a.example/x"]}))])
    result = run_case(plugin, {"text": "great"}, [], model, tools=collect_tools(plugin, {"text": "great"},
                                                                                web_tools(client(api))))
    assert model.calls[0]["tool_choice"] == "required"
    assert body(api)["query"] == "sentiment of great"
    assert result.sources == ["https://a.example/x"] and result.warnings == [] and result.usage["web_calls"] == 1


# --- disk cache (phase 1 of the call-reduction plan) ---------------------------------------------------------------

from venus.cache import DiskCache  # noqa: E402


def cached(api, tmp_path, clock=None):
    cache = DiskCache(tmp_path / "cache", clock=clock) if clock else DiskCache(tmp_path / "cache")
    return ContextDev(api_key="ctx-test", http_client=httpx.Client(transport=httpx.MockTransport(api)),
                      sleep=lambda s: None, cache=cache)


SCRAPE_OK = (200, {"url": "https://a.example/x", "metadata": {"title": "A page"},
                   "markdown": {"requested": True, "success": True, "data": "# Hello"}})


def test_repeated_search_makes_one_http_call(tmp_path):
    api = Api(SEARCH_OK)
    c = cached(api, tmp_path)
    first = c.search("seed investors", num_results=3)
    second = c.search("seed investors", num_results=3)
    assert first == second and len(api.requests) == 1


def test_different_search_is_not_a_hit(tmp_path):
    api = Api(SEARCH_OK, SEARCH_OK)
    c = cached(api, tmp_path)
    c.search("a")
    c.search("b")
    assert len(api.requests) == 2


def test_cache_survives_a_new_client(tmp_path):
    api = Api(SEARCH_OK)
    cached(api, tmp_path).search("seed investors")
    assert cached(Api(), tmp_path).search("seed investors")["results"]  # an empty Api would raise on any HTTP call


def test_news_is_cached(tmp_path):
    api = Api((200, {"data": [{"url": "https://n.example/1", "title": "N", "description": "d",
                               "published_at": "2026-11-01", "source": {"name": "S"}}]}))
    c = cached(api, tmp_path)
    assert c.news("finland startups") == c.news("finland startups") and len(api.requests) == 1


def test_scrape_fresh_skips_the_cache_and_refreshes_it(tmp_path):
    api = Api(SCRAPE_OK, SCRAPE_OK)
    c = cached(api, tmp_path)
    c.scrape("https://a.example/x")
    c.scrape("https://a.example/x", fresh=True)  # must go out again
    assert len(api.requests) == 2
    c.scrape("https://a.example/x")  # the plain call is a hit on the entry fresh=False wrote
    assert len(api.requests) == 2


def test_http_error_is_not_cached(tmp_path):
    api = Api((500, {"message": "boom"}), SEARCH_OK)
    c = cached(api, tmp_path)
    with pytest.raises(WebError):
        c.search("q")
    assert c.search("q")["results"] and len(api.requests) == 2


def test_failed_scrape_with_http_200_is_only_kept_for_an_hour(tmp_path):
    from venus.web import FAIL_TTL

    class Clock:
        now = 1000.0

        def __call__(self):
            return self.now
    clock = Clock()
    failed = (200, {"url": "https://a.example/x", "markdown": {"requested": True, "success": False,
                                                              "error_code": "BLOCKED", "message": "no"}})
    api = Api(failed, SCRAPE_OK)
    c = cached(api, tmp_path, clock=clock)
    for _ in range(2):
        with pytest.raises(WebError):
            c.scrape("https://a.example/x")  # the second one is replayed from the cache
    clock.now += FAIL_TTL + 1
    assert c.scrape("https://a.example/x")["markdown"] == "# Hello" and len(api.requests) == 2


def test_search_cache_expires_after_a_day(tmp_path):
    class Clock:
        now = 1000.0

        def __call__(self):
            return self.now
    clock = Clock()
    api = Api(SEARCH_OK, SEARCH_OK)
    c = cached(api, tmp_path, clock)
    c.search("q")
    clock.now += 23 * 3600
    c.search("q")
    assert len(api.requests) == 1
    clock.now += 2 * 3600
    c.search("q")
    assert len(api.requests) == 2


def test_web_tools_use_the_env_cache_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("VENUS_CACHE_DIR", str(tmp_path / "envcache"))
    api = Api(SEARCH_OK)
    import venus.web as web
    real_client = httpx.Client
    monkeypatch.setattr(web.httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(api)))
    tools = {t.name: t for t in web_tools(environ={"CONTEXT_DEV_API_KEY": "k", "VENUS_CACHE_DIR": str(tmp_path / "envcache")})}
    tools["web_search"].fn({"query": "q"})
    tools["web_search"].fn({"query": "q"})
    assert len(api.requests) == 1 and (tmp_path / "envcache").is_dir()


def test_fresh_scrape_replaces_the_entry_plain_calls_read(tmp_path):
    def page(text):
        return (200, {"url": "https://a.example/x", "metadata": {"title": "A"},
                      "markdown": {"requested": True, "success": True, "data": text}})
    api = Api(page("old"), page("new"))
    c = cached(api, tmp_path)
    assert c.scrape("https://a.example/x")["markdown"] == "old"
    assert c.scrape("https://a.example/x", fresh=True)["markdown"] == "new"
    assert c.scrape("https://a.example/x")["markdown"] == "new" and len(api.requests) == 2


@pytest.mark.parametrize("bad", [{}, {"results": None}, {"message": "oops"}])
def test_odd_200_search_replies_are_not_cached(tmp_path, bad):
    api = Api((200, bad), SEARCH_OK)
    c = cached(api, tmp_path)
    try:
        c.search("q")
    except Exception:
        pass
    assert c.search("q")["results"] and len(api.requests) == 2


def test_odd_200_news_reply_is_not_cached(tmp_path):
    api = Api((200, {"data": None}), (200, {"data": []}))
    c = cached(api, tmp_path)
    try:
        c.news("q")
    except Exception:
        pass
    assert c.news("q") == {"articles": []} and len(api.requests) == 2


def test_unwritable_cache_does_not_lose_a_paid_result(tmp_path):
    blocker = tmp_path / "cache"
    blocker.write_text("a file where the cache folder should be")
    api = Api(SEARCH_OK)
    c = ContextDev(api_key="ctx-test", http_client=httpx.Client(transport=httpx.MockTransport(api)),
                   sleep=lambda s: None, cache=DiskCache(blocker))
    assert c.search("q")["results"]
