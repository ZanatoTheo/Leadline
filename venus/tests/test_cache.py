import json

from venus.cache import DiskCache, cache_from_env


class Clock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


def test_put_get_roundtrip_and_miss(tmp_path):
    cache = DiskCache(tmp_path / "c")
    key = cache.key("search", {"query": "a"})
    assert cache.get(key) is None
    cache.put(key, {"results": [1, 2]})
    assert cache.get(key) == {"results": [1, 2]}


def test_key_ignores_dict_order_and_changes_with_content():
    cache = DiskCache("unused")
    assert cache.key("p", {"a": 1, "b": 2}) == cache.key("p", {"b": 2, "a": 1})
    assert cache.key("p", {"a": 1}) != cache.key("p", {"a": 2})
    assert cache.key("p", {"a": 1}) != cache.key("q", {"a": 1})


def test_ttl_expires_entries(tmp_path):
    clock = Clock()
    cache = DiskCache(tmp_path, ttl=60, clock=clock)
    key = cache.key("x")
    cache.put(key, "v")
    clock.now += 59
    assert cache.get(key) == "v"
    clock.now += 2
    assert cache.get(key) is None


def test_per_call_ttl_overrides_default(tmp_path):
    clock = Clock()
    cache = DiskCache(tmp_path, ttl=None, clock=clock)
    key = cache.key("x")
    cache.put(key, "v")
    clock.now += 500
    assert cache.get(key) == "v"
    assert cache.get(key, ttl=100) is None


def test_corrupt_file_is_a_miss_not_a_crash(tmp_path):
    cache = DiskCache(tmp_path)
    key = cache.key("x")
    cache.put(key, "v")
    (tmp_path / f"{key}.json").write_text("{not json")
    assert cache.get(key) is None


def test_write_leaves_no_temp_files_and_creates_the_folder(tmp_path):
    folder = tmp_path / "deep" / "cache"
    cache = DiskCache(folder)
    cache.put(cache.key("x"), {"a": 1})
    assert [p.suffix for p in folder.iterdir()] == [".json"]
    assert json.loads(next(folder.iterdir()).read_text())["v"] == {"a": 1}


def test_cache_from_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    default = cache_from_env({})
    assert default is not None and default.directory == tmp_path / ".venus_cache"
    custom = cache_from_env({"VENUS_CACHE_DIR": str(tmp_path / "elsewhere")})
    assert custom.directory == tmp_path / "elsewhere"
    assert cache_from_env({"VENUS_CACHE_DIR": "off"}) is None


def test_non_number_timestamp_is_a_miss_not_a_crash(tmp_path):
    cache = DiskCache(tmp_path, ttl=60)
    key = cache.key("x")
    for bad in (None, "yesterday", [1]):
        (tmp_path / f"{key}.json").write_text(json.dumps({"t": bad, "v": "v"}))
        assert cache.get(key) is None


def test_relative_and_blank_cache_dirs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert cache_from_env({"VENUS_CACHE_DIR": "rel/dir"}).directory == tmp_path / "rel" / "dir"
    assert cache_from_env({"VENUS_CACHE_DIR": "   "}).directory == tmp_path / ".venus_cache"
