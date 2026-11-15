"""A small on-disk cache for repeated external calls (web search, scrape, news; later model replies).

One JSON file per entry, named by the SHA-1 of the key parts. A miss, an expired entry and a damaged file all give
`None`, so a bad cache never breaks a run. Writes go to a temp file first, so a crash leaves no half-written entry.
Only store results you trust: callers decide what is worth caching (errors are not)."""
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

DEFAULT_DIR = ".venus_cache"


class DiskCache:
    def __init__(self, directory, ttl: float | None = None, clock=time.time):
        self.directory = Path(directory)
        self.ttl = ttl
        self._clock = clock

    @staticmethod
    def key(*parts) -> str:
        """Stable key for any JSON-like parts (dict order does not matter). Never include secrets in `parts`."""
        raw = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def _file(self, key: str) -> Path:
        return self.directory / f"{key}.json"

    def get(self, key: str, ttl: float | None = None):
        """The stored value, or None on a miss, an expired entry or a damaged file. `ttl` overrides the default."""
        try:
            entry = json.loads(self._file(key).read_text(encoding="utf-8"))
            stored_at, value = entry["t"], entry["v"]
        except (OSError, ValueError, KeyError, TypeError):
            return None
        if isinstance(stored_at, bool) or not isinstance(stored_at, (int, float)):
            return None  # damaged entry
        limit = self.ttl if ttl is None else ttl
        if limit is not None and self._clock() - stored_at > limit:
            return None
        return value

    def put(self, key: str, value) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(dir=self.directory, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"t": self._clock(), "v": value}, f, ensure_ascii=False)
            os.replace(temp, self._file(key))
        except BaseException:
            try:
                os.unlink(temp)
            except OSError:
                pass
            raise

    def delete(self, key: str) -> None:
        """Drop one entry; a missing file or an unwritable folder is ignored."""
        try:
            self._file(key).unlink(missing_ok=True)
        except OSError:
            pass


def cache_from_env(environ=None, ttl: float | None = None) -> DiskCache | None:
    """`VENUS_CACHE_DIR` names the folder (default `.venus_cache` in the current folder); `off` turns caching off."""
    environ = os.environ if environ is None else environ
    folder = (environ.get("VENUS_CACHE_DIR") or "").strip() or DEFAULT_DIR
    if folder.lower() in ("off", "none", "0"):
        return None
    return DiskCache(Path(folder).expanduser().resolve(), ttl=ttl)  # absolute, so the folder doesn't move with cwd


def model_cache_from_env(environ=None) -> DiskCache | None:
    """Cache for model replies: only when `VENUS_MODEL_CACHE` is `1`/`true`/`on`/`yes`. It lives in a `models` folder
    inside the folder `cache_from_env` picks, and is off when that is off. Replies never expire: the key holds the
    model id, so a different model asks again."""
    environ = os.environ if environ is None else environ
    if (environ.get("VENUS_MODEL_CACHE") or "").strip().lower() not in ("1", "true", "on", "yes"):
        return None
    base = cache_from_env(environ)
    return None if base is None else DiskCache(base.directory / "models")
