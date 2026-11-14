"""Plugins: how a task plugs into Venus.

A plugin is a folder with `plugin.json` (see schemas/plugin.schema.json):
    name, version, brief, input_schema, output_schema (files in the folder), checker ("module:function"),
    optional tools ("module:function"), optional seed_tendencies [{id, text}], optional settings_schema (a file or
    an inline JSON Schema for the plugin's own strategy settings; see strategy.check_settings).
A `gate.py` with `gate(settings, cases) -> {passed, metrics, reasons}` in the folder is the plugin's free gate
(found by name; see venus.gate).
The checker has the signature `check(input, output, expected) -> Score | {total, parts, reasons}`, total in [0, 1].
The optional tools factory has the signature `make_tools(input) -> list`.
"""
import hashlib
import importlib.util
import inspect
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, best_match

from .errors import InputError, PluginError, join_path
from .schemas import load_schema
from .tendency import Tendency


@dataclass(frozen=True)
class Score:
    total: float
    parts: dict = field(default_factory=dict)
    reasons: list = field(default_factory=list)

    @classmethod
    def from_value(cls, value) -> "Score":
        """Accept a Score or a {total, parts, reasons} mapping; raise ValueError if it breaks the rules."""
        if isinstance(value, Score):
            total, parts, reasons = value.total, value.parts, value.reasons
        elif isinstance(value, dict):
            total, parts, reasons = value.get("total"), value.get("parts", {}), value.get("reasons", [])
        else:
            raise ValueError(f"a score must be a Score or a dict, got {type(value).__name__}")
        if isinstance(total, bool) or not isinstance(total, (int, float)) or not math.isfinite(total):
            raise ValueError(f"score total must be a finite number, got {total!r}")
        if not 0 <= total <= 1:
            raise ValueError(f"score total must be in [0, 1], got {total}")
        if not isinstance(parts, dict) or not all(
            isinstance(k, str) and not isinstance(v, bool) and isinstance(v, (int, float)) and math.isfinite(v)
            for k, v in parts.items()
        ):
            raise ValueError("score parts must map names to finite numbers")
        if not isinstance(reasons, list) or not all(isinstance(r, str) for r in reasons):
            raise ValueError("score reasons must be a list of strings")
        return cls(total=float(total), parts={k: float(v) for k, v in parts.items()}, reasons=list(reasons))

    def to_dict(self) -> dict:
        return {"total": self.total, "parts": dict(self.parts), "reasons": list(self.reasons)}


def _validate(schema: dict, value, path: str, code: str) -> None:
    error = best_match(Draft202012Validator(schema).iter_errors(value))
    if error is not None:
        raise InputError(code, error.message, path=join_path(path, error.absolute_path))


@dataclass(frozen=True)
class Plugin:
    name: str
    version: str
    brief: str
    root: Path
    input_schema: dict
    output_schema: dict
    seed_tendencies: tuple
    checker: Callable
    tools_factory: Callable | None = None
    web_enabled: bool = True  # built-in web tools; manifest "web": false turns them off
    cala_enabled: bool = False  # built-in Cala tools in run mode; manifest "cala": true turns them on
    settings_schema: dict | None = None  # the plugin's own strategy settings (keys besides the core ones)
    gate_hook: Callable | None = None  # gate.py:gate(settings, cases) in the plugin folder, if present (venus.gate)

    def validate_input(self, value, path: str = "input") -> None:
        _validate(self.input_schema, value, path, "input_invalid")

    def validate_output(self, value, path: str = "output", code: str = "output_invalid") -> None:
        _validate(self.output_schema, value, path, code)

    def check(self, input, output, expected) -> Score:
        """Score `output` against `expected` with the plugin's checker."""
        try:
            result = self.checker(input, output, expected)
        except Exception as e:
            raise PluginError("plugin_checker_failed", f"{self.name} checker raised {type(e).__name__}: {e}") from e
        try:
            return Score.from_value(result)
        except ValueError as e:
            raise PluginError("plugin_bad_score", f"{self.name} checker: {e}") from None

    def tools(self, input, settings: dict | None = None) -> list:
        """The plugin's tools for this input, or [] if it has none. A factory that takes a second parameter gets
        the strategy's plugin settings."""
        if self.tools_factory is None:
            return []
        try:
            tools = self.tools_factory(input, settings or {}) if _takes_two(self.tools_factory) \
                else self.tools_factory(input)
        except Exception as e:
            raise PluginError("plugin_tools_failed", f"{self.name} tools raised {type(e).__name__}: {e}") from e
        if not isinstance(tools, list):
            raise PluginError("plugin_tools_failed", f"{self.name} tools must return a list")
        return tools


def _takes_two(fn) -> bool:
    try:
        params = inspect.signature(fn).parameters.values()
    except (TypeError, ValueError):
        return False
    positional = [p for p in params if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    return len(positional) >= 2 or any(p.kind == p.VAR_POSITIONAL for p in params)


def _inside(root: Path, rel: str) -> Path:
    target = (root / rel).resolve()
    if not target.is_relative_to(root):
        raise PluginError("plugin_manifest_invalid", f"{rel!r} points outside the plugin folder")
    return target


def _load_json_schema(root: Path, rel: str, field_name: str) -> dict:
    path = _inside(root, rel)
    if not path.is_file():
        raise PluginError("plugin_schema_missing", f"{field_name} file not found: {rel}", path=field_name)
    try:
        schema = json.loads(path.read_text())
        Draft202012Validator.check_schema(schema)
    except (json.JSONDecodeError, SchemaError) as e:
        raise PluginError("plugin_schema_invalid", f"{rel}: {e}", path=field_name) from None
    return schema


def _load_callable(root: Path, plugin_name: str, ref: str, field_name: str, missing_code: str) -> Callable:
    module_part, func_name = ref.split(":")
    file = _inside(root, module_part.replace(".", "/") + ".py")
    if not file.is_file():
        raise PluginError(missing_code, f"{field_name} module not found: {file.name}", path=field_name)
    digest = hashlib.sha1(str(file).encode()).hexdigest()[:10]
    mod_name = f"venus_plugin_{plugin_name.replace('-', '_')}_{module_part.replace('.', '_')}_{digest}"
    module = sys.modules.get(mod_name)
    if module is None:
        spec = importlib.util.spec_from_file_location(mod_name, file)
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception as e:
            sys.modules.pop(mod_name, None)
            raise PluginError("plugin_import_failed", f"{file.name}: {type(e).__name__}: {e}", path=field_name) from e
    fn = getattr(module, func_name, None)
    if not callable(fn):
        raise PluginError(missing_code, f"{ref} is not a function in the plugin", path=field_name)
    return fn


CORE_SETTING_KEYS = ("max_turns", "max_web_calls")  # strategy.CORE_SETTINGS; Venus owns these


def _settings_schema(root: Path, value) -> dict | None:
    """The plugin's settings schema: a closed object schema (properties, additionalProperties false, no top-level
    $ref) that declares none of the core keys, so every key a strategy may carry is listed and typed."""
    if value is None:
        return None
    if isinstance(value, str):
        schema = _load_json_schema(root, value, "settings_schema")
    else:
        try:
            Draft202012Validator.check_schema(value)
        except SchemaError as e:
            raise PluginError("plugin_schema_invalid", f"settings_schema: {e.message}",
                              path="settings_schema") from None
        schema = value

    def bad(why):
        return PluginError("plugin_schema_invalid", f"settings_schema: {why}", path="settings_schema")
    if "$ref" in schema or schema.get("type") != "object":
        raise bad('must be {"type": "object", ...} itself, not a $ref')
    if not isinstance(schema.get("properties"), dict) or not schema["properties"]:
        raise bad("must list its keys under properties")
    if schema.get("additionalProperties") is not False:
        raise bad("must set additionalProperties: false, so unknown keys are refused")
    core = sorted(set(schema["properties"]) & set(CORE_SETTING_KEYS))
    if core:
        raise bad(f"declares core key(s) {core}; Venus applies those itself")
    return schema


def _gate_hook(root: Path, name: str):
    """gate.py:gate, if the file exists. A gate.py that can't be loaded must not stop the plugin from serving runs,
    so it becomes a gate that rejects every strategy with the load error."""
    if not (root / "gate.py").is_file():
        return None
    try:
        return _load_callable(root, name, "gate:gate", "gate", "plugin_gate_missing")
    except PluginError as e:
        message = e.message

        def broken(settings, cases):
            raise RuntimeError(f"gate.py could not be loaded: {message}")
        return broken


def _no_checker(name: str):
    def check(input, output, expected):
        raise PluginError("plugin_checker_missing", f"{name} was loaded for runs only; it has no checker")
    return check


def load_plugin(path, runtime_only: bool = False) -> Plugin:
    """Load and check the plugin in folder `path`. Any problem raises one PluginError naming it. `runtime_only=True`
    (the exported agent) neither needs nor loads the checker or gate.py: runs never score."""
    root = Path(path).resolve()
    manifest_file = root / "plugin.json"
    if not manifest_file.is_file():
        raise PluginError("plugin_manifest_missing", f"no plugin.json in {root}")
    try:
        manifest = json.loads(manifest_file.read_text())
    except json.JSONDecodeError as e:
        raise PluginError("plugin_manifest_invalid", f"plugin.json is not valid JSON: {e}") from None
    error = best_match(Draft202012Validator(load_schema("plugin")).iter_errors(manifest))
    if error is not None:
        raise PluginError("plugin_manifest_invalid", error.message, path=join_path("", error.absolute_path))
    name = manifest["name"]
    tools_ref = manifest.get("tools")
    return Plugin(
        name=name,
        version=manifest["version"],
        brief=manifest["brief"],
        root=root,
        input_schema=_load_json_schema(root, manifest["input_schema"], "input_schema"),
        output_schema=_load_json_schema(root, manifest["output_schema"], "output_schema"),
        seed_tendencies=tuple(Tendency.from_dict(t) for t in manifest.get("seed_tendencies", [])),
        checker=_no_checker(name) if runtime_only else _load_callable(root, name, manifest["checker"], "checker",
                                                                     "plugin_checker_missing"),
        tools_factory=_load_callable(root, name, tools_ref, "tools", "plugin_tools_missing") if tools_ref else None,
        web_enabled=manifest.get("web", True),
        cala_enabled=manifest.get("cala", False),
        settings_schema=_settings_schema(root, manifest.get("settings_schema")),
        gate_hook=None if runtime_only else _gate_hook(root, name),
    )


def load_plugins(directory, runtime_only: bool = False) -> dict:
    """Load every plugin in the subfolders of `directory` that hold a plugin.json. Returns {name: Plugin}."""
    plugins = {}
    for sub in sorted(Path(directory).iterdir()):
        if sub.is_dir() and (sub / "plugin.json").is_file():
            plugin = load_plugin(sub, runtime_only=runtime_only)
            if plugin.name in plugins:
                raise PluginError("plugin_duplicate", f"two plugins are named {plugin.name!r}")
            plugins[plugin.name] = plugin
    return plugins
