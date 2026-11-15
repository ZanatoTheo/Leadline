"""The mode gate. Every request is either:
- training: {venus_version, plugin, mode: "training", cases: [{id, input, expected}]}, where `expected` is the
  validated reference output for that input; or
- run: {venus_version, plugin, mode: "run", strategy, input}, where the strategy exists, is "validated", and was
  made for this plugin's name and version.
Anything else is refused with a VenusError carrying a stable code and the path of the bad field."""
from dataclasses import dataclass
from typing import Mapping

from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match

from .errors import InputError, ModeError, PluginError, StrategyError, join_path
from .plugin import Plugin
from .schemas import load_schema
from .strategy import Strategy, StrategyStore, check_settings

VENUS_VERSION = "1"
MODES = ("training", "run")


@dataclass(frozen=True)
class Case:
    id: str
    input: object
    expected: object


@dataclass(frozen=True)
class TrainingRequest:
    plugin: Plugin
    cases: tuple
    mode: str = "training"


@dataclass(frozen=True)
class RunRequest:
    plugin: Plugin
    strategy: Strategy
    input: object
    mode: str = "run"


def _check_envelope(raw: dict, mode: str) -> None:
    full = load_schema("request")
    sub = {"$schema": full["$schema"], "$defs": full["$defs"], "$ref": f"#/$defs/{mode}"}
    error = best_match(Draft202012Validator(sub).iter_errors(raw))
    if error is not None:
        raise InputError("request_invalid", error.message, path=join_path("", error.absolute_path) or None)


def check_request(raw, plugins: Mapping[str, Plugin], strategies: StrategyStore):
    """Check a raw request (parsed JSON) and return a TrainingRequest or a RunRequest."""
    if not isinstance(raw, dict):
        raise InputError("request_invalid", "a request must be a JSON object")
    mode = raw.get("mode")
    if not isinstance(mode, str) or mode not in MODES:
        raise ModeError("unknown_mode", f"mode must be 'training' or 'run', got {mode!r}", path="mode")
    if raw.get("venus_version") != VENUS_VERSION:
        raise InputError("version_unsupported", f"venus_version must be {VENUS_VERSION!r}, got "
                                                f"{raw.get('venus_version')!r}", path="venus_version")

    if mode == "training":
        if "strategy" in raw:
            raise InputError("strategy_not_allowed", "training runs the base model; drop 'strategy'",
                             path="strategy")
        if "cases" not in raw:
            raise InputError("cases_missing", "training needs 'cases': [{id, input, expected}]", path="cases")
        if raw["cases"] == []:
            raise InputError("cases_empty", "training needs at least one case", path="cases")
        if isinstance(raw["cases"], list):
            for i, case in enumerate(raw["cases"]):
                if isinstance(case, dict) and "expected" not in case:
                    raise InputError("expected_missing", "every training case needs a validated 'expected'",
                                     path=f"cases[{i}].expected")
    else:
        if "expected" in raw:
            raise InputError("expected_not_allowed", "run requests don't take 'expected'", path="expected")
        if "strategy" not in raw:
            raise StrategyError("strategy_missing", "run requests need a validated strategy", path="strategy")

    _check_envelope(raw, mode)

    plugin = plugins.get(raw["plugin"])
    if plugin is None:
        raise PluginError("plugin_not_found", f"no plugin named {raw['plugin']!r}", path="plugin")

    if mode == "training":
        seen = set()
        cases = []
        for i, c in enumerate(raw["cases"]):
            if c["id"] in seen:
                raise InputError("case_id_duplicate", f"case id {c['id']!r} is used twice", path=f"cases[{i}].id")
            seen.add(c["id"])
            plugin.validate_input(c["input"], path=f"cases[{i}].input")
            plugin.validate_output(c["expected"], path=f"cases[{i}].expected", code="expected_invalid")
            cases.append(Case(id=c["id"], input=c["input"], expected=c["expected"]))
        return TrainingRequest(plugin=plugin, cases=tuple(cases))

    strategy = run_strategy(plugin, strategies, raw["strategy"])
    plugin.validate_input(raw["input"], path="input")
    return RunRequest(plugin=plugin, strategy=strategy, input=raw["input"])


def run_strategy(plugin: Plugin, strategies: StrategyStore, strategy_id: str) -> Strategy:
    """The strategy a run of `plugin` may use: it exists, is validated, was made for this plugin version and its
    settings are valid. Raises StrategyError otherwise."""
    strategy = strategies.get(strategy_id)
    if not strategy.is_validated:
        raise StrategyError("strategy_not_validated", f"strategy {strategy.id!r} has status {strategy.status!r}; "
                                                      "run mode needs 'validated'", path="strategy")
    if strategy.plugin != plugin.name or strategy.plugin_version != plugin.version:
        raise StrategyError("strategy_plugin_mismatch",
                            f"strategy {strategy.id!r} is for {strategy.plugin} {strategy.plugin_version}, "
                            f"not {plugin.name} {plugin.version}", path="strategy")
    check_settings(plugin, strategy.settings)
    return strategy
