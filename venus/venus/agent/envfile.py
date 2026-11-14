"""Read KEY=VALUE lines from a .env file into the environment. Values already set in the shell win."""
import os
from pathlib import Path


def find_env_file(environ=None, start=None) -> Path | None:
    """`VENUS_ENV_FILE` if set, else the first `.env` found walking up from `start` (default: current folder)."""
    environ = os.environ if environ is None else environ
    if environ.get("VENUS_ENV_FILE"):
        return Path(environ["VENUS_ENV_FILE"]).expanduser()
    folder = Path(start or Path.cwd()).resolve()
    for candidate in [folder, *folder.parents]:
        if (candidate / ".env").is_file():
            return candidate / ".env"
    return None


def load_env(path=None, environ=None, start=None) -> dict:
    """Load `path` (default: `find_env_file()`) into `environ` (default os.environ) without overriding existing keys.
    Returns the keys it set. A missing file is not an error."""
    environ = os.environ if environ is None else environ
    path = Path(path) if path is not None else find_env_file(environ, start)
    if path is None or not path.is_file():
        return {}
    loaded = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if not key or key in environ:
            continue
        environ[key] = value
        loaded[key] = value
    return loaded
