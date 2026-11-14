"""Context.dev, for real: search, scrape and news once each (fresh), then a repeat search served by the disk cache."""
from conftest import need

from venus.cache import DiskCache
from venus.web import ContextDev


def test_context_dev_search_scrape_news_and_cache(counter, tmp_path):
    need("CONTEXT_DEV_API_KEY|CONTEXTDEV_API_KEY")
    web = ContextDev(http_client=counter.client, cache=DiskCache(tmp_path))

    found = web.search("Finnish seed stage venture capital funds", num_results=3)
    assert found["results"] and all(r["url"] for r in found["results"])
    page = web.scrape(found["results"][0]["url"], fresh=True, max_chars=2000)
    assert page["markdown"]
    news = web.news("Nordic startup funding round", limit=3)
    assert isinstance(news["articles"], list)
    calls = counter.count
    print(f"\nCONTEXT.DEV search={len(found['results'])} scrape_chars={len(page['markdown'])} "
          f"news={len(news['articles'])} http_calls={calls}")

    again = web.search("Finnish seed stage venture capital funds", num_results=3)
    assert again == found and counter.count == calls, "repeat search should be a cache hit (0 HTTP calls)"
