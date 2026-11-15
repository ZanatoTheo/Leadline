"""Venus errors. Each has a stable `code` (for callers and the HTTP layer) and, when known, the JSON `path` of the
bad field, e.g. `cases[2].input.amount`."""


class VenusError(Exception):
    def __init__(self, code: str, message: str, path: str | None = None):
        super().__init__(f"{code}: {message}" + (f" (at {path})" if path else ""))
        self.code = code
        self.message = message
        self.path = path

    def to_dict(self) -> dict:
        d = {"code": self.code, "message": self.message}
        if self.path:
            d["path"] = self.path
        return d


class PluginError(VenusError):
    """A plugin is missing, broken, or misbehaved (bad manifest, checker failure, bad score)."""


class StrategyError(VenusError):
    """A strategy is missing, invalid, not validated, or meant for another plugin."""


class InputError(VenusError):
    """A request or one of its inputs doesn't match the contract."""


class ModeError(VenusError):
    """A request is neither `training` nor `run`."""


class ModelError(VenusError):
    """A model call failed: config missing, auth, bad request, endpoint unavailable, or an unreadable reply."""


class BudgetExceeded(VenusError):
    """A budget cap (model calls, tokens, or seconds) was reached before a call."""

    def __init__(self, message: str):
        super().__init__("budget_exceeded", message)


class WebError(VenusError):
    """A web tool call failed (config, HTTP error, timeout, or a failed result). Shown to the agent as a tool error."""


class CalaError(VenusError):
    """A Cala tool call failed: no key for an uncached call (cala_config_missing), a bad VENUS_CALA_MAX_CALLS
    (cala_config_invalid), the per-run call cap
    (cala_budget), a bad argument (cala_bad_argument), or an HTTP/network/JSON failure (cala_failed).
    Shown to the agent as a tool error."""


def join_path(prefix: str, parts) -> str:
    """Build a JSON path like `cases[2].input.text` from a prefix and jsonschema path parts."""
    out = prefix or ""
    for part in parts:
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            out += f".{part}" if out else str(part)
    return out
