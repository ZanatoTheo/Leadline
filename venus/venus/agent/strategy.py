"""Strategies: a base model plus behavioral tendencies for one plugin version, stored as strategies/<id>.json.
Only a strategy with status "validated" may serve run requests. For now they're written by hand; the trial engine
will write them later.

A strategy may carry `settings`: typed knobs. Core keys (CORE_SETTINGS) are applied by Venus to every run; any other
key belongs to the plugin and must be declared in its `settings_schema`. `check_settings` enforces both."""
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match

from .errors import StrategyError, join_path
from .schemas import load_schema
from .tendency import Tendency

ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
CORE_SETTINGS = {  # applied by Venus: run_case limits
    "max_turns": {"type": "integer", "minimum": 1, "maximum": 20},
    "max_web_calls": {"type": "integer", "minimum": 0, "maximum": 40},
}


def check_settings(plugin, settings: dict) -> None:
    """Raise StrategyError("strategy_invalid") unless every core key has the right type and every other key is
    declared (and valid) in the plugin's settings_schema."""
    core = {k: v for k, v in settings.items() if k in CORE_SETTINGS}
    rest = {k: v for k, v in settings.items() if k not in CORE_SETTINGS}
    for k, v in core.items():  # JSON Schema "integer" takes 2.0 and the runner's limits do not
        if isinstance(v, bool) or not isinstance(v, int):
            raise StrategyError("strategy_invalid", f"settings: {k} must be a whole number, got {v!r}",
                                path=f"settings.{k}")
    schema = {"type": "object", "properties": CORE_SETTINGS}
    error = best_match(Draft202012Validator(schema).iter_errors(core))
    if error is not None:
        raise StrategyError("strategy_invalid", f"settings: {error.message}",
                            path=join_path("settings", error.absolute_path))
    if not rest:
        return
    plugin_schema = getattr(plugin, "settings_schema", None)
    declared = set((plugin_schema or {}).get("properties", {}))
    unknown = sorted(set(rest) - declared)
    if unknown:
        known = sorted(set(CORE_SETTINGS) | declared)
        raise StrategyError("strategy_invalid", f"unknown setting(s) {unknown} for plugin {plugin.name}; known: "
                                                f"{known}", path=f"settings.{unknown[0]}")
    try:
        error = best_match(Draft202012Validator(plugin_schema).iter_errors(rest))
    except Exception as e:  # e.g. a $ref the validator cannot resolve
        raise StrategyError("strategy_invalid", f"settings: the plugin's settings schema could not be applied: "
                                                f"{type(e).__name__}: {e}", path="settings") from None
    if error is not None:
        raise StrategyError("strategy_invalid", f"settings: {error.message}",
                            path=join_path("settings", error.absolute_path))



@dataclass(frozen=True)
class Strategy:
    id: str
    plugin: str
    plugin_version: str
    status: str
    base_model: dict
    tendencies: tuple
    created_at: str
    notes: str = ""
    settings: dict = field(default_factory=dict)

    @property
    def core_settings(self) -> dict:
        """The keys Venus applies itself (run_case limits)."""
        return {k: v for k, v in self.settings.items() if k in CORE_SETTINGS}

    @property
    def plugin_settings(self) -> dict:
        """The keys for the plugin."""
        return {k: v for k, v in self.settings.items() if k not in CORE_SETTINGS}

    @property
    def is_validated(self) -> bool:
        return self.status == "validated"

    @classmethod
    def from_dict(cls, d: dict) -> "Strategy":
        return cls(
            id=d["id"],
            plugin=d["plugin"],
            plugin_version=d["plugin_version"],
            status=d["status"],
            base_model=dict(d["base_model"]),
            tendencies=tuple(Tendency.from_dict(t) for t in d["tendencies"]),
            created_at=d["created_at"],
            notes=d.get("notes", ""),
            settings=dict(d.get("settings") or {}),
        )


class StrategyStore:
    """Reads strategy files from one folder."""

    def __init__(self, directory):
        self.directory = Path(directory).resolve()

    def get(self, strategy_id: str) -> Strategy:
        if not isinstance(strategy_id, str) or not ID_RE.fullmatch(strategy_id) or set(strategy_id) == {"."}:
            raise StrategyError("strategy_not_found", f"no strategy {strategy_id!r}")
        file = self.directory / f"{strategy_id}.json"
        if not file.is_file():
            raise StrategyError("strategy_not_found", f"no strategy {strategy_id!r} in {self.directory}")
        try:
            data = json.loads(file.read_text())
        except json.JSONDecodeError as e:
            raise StrategyError("strategy_invalid", f"{file.name} is not valid JSON: {e}") from None
        error = best_match(Draft202012Validator(load_schema("strategy")).iter_errors(data))
        if error is not None:
            raise StrategyError("strategy_invalid", f"{file.name}: {error.message}",
                                path=join_path("", error.absolute_path))
        if data["id"] != strategy_id:
            raise StrategyError("strategy_invalid", f"{file.name} holds id {data['id']!r}, not {strategy_id!r}")
        return Strategy.from_dict(data)

    def ids(self) -> list:
        return sorted(f.stem for f in self.directory.glob("*.json"))
