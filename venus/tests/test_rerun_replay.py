"""An identical rerun must replay from cache (phase 9 review): web results that never expire in training (A), failed
web results replayed for an hour (B), the first invalid answer recorded (D), research's token room (E), and no
`fresh` scrape in training (F). Fake HTTP and a fake clock only."""
import json

import httpx
import pytest

from venus.cache import DiskCache
from venus.errors import WebError
from venus.fake import FakeModel, fake_text
from venus.plugin import load_plugin
from venus.web import FAIL_TTL, FRESH_TTL, ContextDev, web_tools

SEARCH = {"results": [{"url": "https://a.example", "title": "A", "description": "a"}]}
NEWS = {"data": [{"url": "https://n.example", "title": "N"}]}
GOOD = json.dumps({"output": {"label": "positive"}, "sources": []})


class Clock:
    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self):
        return self.now


class Server:
    """Serves {path: (status, body)} and counts requests."""
    def __init__(self, routes):
        self.routes, self.count = routes, 0

    def __call__(self, request):
        self.count += 1
        status, body = self.routes[request.url.path]
        return httpx.Response(status, json=body)


def client(tmp_path, routes, clock, **kw):
    server = Server(routes)
    cd = ContextDev(api_key="k", http_client=httpx.Client(transport=httpx.MockTransport(server)),
                    cache=DiskCache(tmp_path / "web", clock=clock), sleep=lambda s: None, **kw)
    return cd, server


# --- A: training web results never expire --------------------------------------------------------------------------

def test_served_search_results_expire_after_a_day(tmp_path):
    clock = Clock()
    cd, server = client(tmp_path, {"/v1/web/search": (200, SEARCH)}, clock)
    cd.search("q")
    clock.now += FRESH_TTL + 1
    cd.search("q")
    assert server.count == 2


def test_training_search_and_news_results_never_expire(tmp_path):
    clock = Clock()
    cd, server = client(tmp_path, {"/v1/web/search": (200, SEARCH), "/v1/news/search": (200, NEWS)}, clock,
                        fresh_ttl=None)
    cd.search("q")
    cd.news("q")
    clock.now += 30 * 24 * 3600
    assert cd.search("q")["results"][0]["url"] == "https://a.example" and cd.news("q")["articles"]
    assert server.count == 2


# --- B: failed results are replayed for an hour --------------------------------------------------------------------

def test_a_failed_scrape_is_replayed_for_an_hour_then_asked_again(tmp_path):
    clock = Clock()
    blocked = {"markdown": {"success": False, "error_code": "BLOCKED", "message": "robots"}}
    cd, server = client(tmp_path, {"/v1/web/scrape": (200, blocked)}, clock)
    for _ in range(2):
        with pytest.raises(WebError) as e:
            cd.scrape("https://x.example/p")
        assert "BLOCKED" in e.value.message
    assert server.count == 1
    clock.now += FAIL_TTL + 1
    with pytest.raises(WebError):
        cd.scrape("https://x.example/p")
    assert server.count == 2


def test_a_client_error_is_replayed_with_the_same_message(tmp_path):
    clock = Clock()
    cd, server = client(tmp_path, {"/v1/web/search": (404, {"error_code": "NOT_FOUND", "message": "gone"})}, clock)
    messages = []
    for _ in range(2):
        with pytest.raises(WebError) as e:
            cd.search("q")
        messages.append(e.value.message)
    assert server.count == 1 and messages[0] == messages[1] and "gone" in messages[0]


@pytest.mark.parametrize("status", [401, 403, 429, 500, 503])
def test_auth_rate_limit_and_server_errors_are_never_stored(tmp_path, status):
    clock = Clock()
    cd, server = client(tmp_path, {"/v1/web/search": (status, {"message": "no"})}, clock)
    for _ in range(2):
        with pytest.raises(WebError):
            cd.search("q")
    assert server.count == (4 if status == 429 else 2)  # a 429 is retried once inside each call


def test_a_success_after_a_stored_failure_wins(tmp_path):
    clock = Clock()
    cd, server = client(tmp_path, {"/v1/web/search": (404, {"message": "gone"})}, clock)
    with pytest.raises(WebError):
        cd.search("q")
    server.routes["/v1/web/search"] = (200, SEARCH)
    clock.now += FAIL_TTL + 1
    assert cd.search("q")["results"]
    server.routes["/v1/web/search"] = (404, {"message": "gone"})
    assert cd.search("q")["results"] and server.count == 2  # the stored success is read first


# --- F: no fresh scrape in training --------------------------------------------------------------------------------

def test_training_tools_offer_no_fresh_scrape_and_ignore_it(tmp_path):
    clock = Clock()
    page = {"url": "https://x.example", "markdown": {"success": True, "data": "hello"}}
    cd, server = client(tmp_path, {"/v1/web/scrape": (200, page)}, clock)
    tools = {t.name: t for t in web_tools(cd, allow_fresh=False)}
    assert "fresh" not in tools["web_scrape"].parameters["properties"]
    tools["web_scrape"].fn({"url": "https://x.example"})
    tools["web_scrape"].fn({"url": "https://x.example", "fresh": True})
    assert server.count == 1
    assert "fresh" in {t.name: t for t in web_tools(cd)}["web_scrape"].parameters["properties"]


# --- D: the first invalid answer is recorded -------------------------------------------------------------------------

def test_an_invalid_first_answer_is_in_the_trace_and_warnings(toy_plugin_dir):
    from venus.runner import run_case
    result = run_case(load_plugin(toy_plugin_dir), {"text": "great"}, [],
                      FakeModel([fake_text("not json"), fake_text(GOOD)]))
    bad = [e for e in result.trace if e.get("type") == "invalid_answer"]
    assert len(bad) == 1 and bad[0]["error"]
    assert any("repaired" in w for w in result.warnings)


# --- D + E: the research brief states the limits; research has room to answer --------------------------------------

def test_research_brief_states_the_limits_and_gives_room(toy_plugin_dir, monkeypatch):
    import venus.training as training
    task = training.research_task(load_plugin(toy_plugin_dir), n=5)
    assert "400 characters" in task.brief and "at most 5" in task.brief
    seen = {}

    def spy(plugin, input, tendencies, model, tools=(), **kw):
        seen.update(kw)
        raise training.VenusError("model_unavailable", "stop")
    monkeypatch.setattr(training, "run_case", spy)
    with pytest.raises(training.VenusError):
        training.research(load_plugin(toy_plugin_dir), [], FakeModel([]), [])
    assert seen["max_tokens"] >= 4000
