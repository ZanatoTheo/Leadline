"""The free gate: reject a bad strategy before spending a single model call.

`gate(plugin, strategy, cases) -> {passed, metrics, reasons}`

Core checks (any plugin):
- the strategy is for this plugin name and version;
- its settings pass `strategy.check_settings`;
- it has at most runner.MAX_TENDENCIES tendencies;
- there is at least one case, and every case input and expected value pass the plugin's schemas.
Cost per case, from the strategy's limits: model calls and web calls are upper bounds (max_turns + a reminder and a
repair; max_web_calls). Input tokens are a rough estimate (about 4 characters a token): the system prompt and input
resent on every call, plus every allowed web result at the runner's size cap, counted on every call. Optional caps
(`max_model_calls_per_case`, `max_input_tokens_per_case`) turn an estimate into a rejection.

Then the plugin's own gate, when its folder has `gate.py` with `gate(settings, cases)`: it gets the strategy's plugin
settings (no core keys) and the cases that passed the core checks, as dicts, and returns {passed, metrics, reasons}. Its metrics go under
metrics["plugin"]. A plugin gate that raises or returns a bad reply counts as a rejection, never a crash.
"""
import json

from .errors import InputError, StrategyError
from .runner import MAX_TENDENCIES, MAX_TOOL_CHARS, system_prompt
from .strategy import CORE_SETTINGS, check_settings
from .training import TRAIN_CASE_LIMITS

EXTRA_CALLS = 2  # the runner may add a search reminder and one repair
CHARS_PER_TOKEN = 4


def _as_dict(case):
    if isinstance(case, dict):
        return {"id": case.get("id"), "input": case.get("input"), "expected": case.get("expected")}
    if all(hasattr(case, k) for k in ("id", "input", "expected")):
        return {"id": case.id, "input": case.input, "expected": case.expected}
    return None


def _limit(strategy, key) -> int:
    value = strategy.settings.get(key)
    ok = isinstance(value, int) and not isinstance(value, bool)
    return value if ok else TRAIN_CASE_LIMITS[key]


def gate(plugin, strategy, cases, max_model_calls_per_case: int | None = None,
         max_input_tokens_per_case: int | None = None) -> dict:
    reasons, metrics = [], {}
    converted = []
    for i, c in enumerate(cases):
        d = _as_dict(c)
        if d is None:
            reasons.append(f"cases[{i}] is not a case ({type(c).__name__}); need {{id, input, expected}}")
        else:
            converted.append(d)
    cases = converted

    if strategy.plugin != plugin.name or strategy.plugin_version != plugin.version:
        reasons.append(f"strategy is for {strategy.plugin} {strategy.plugin_version}, not plugin "
                       f"{plugin.name} version {plugin.version}")
    try:
        check_settings(plugin, strategy.settings)
    except StrategyError as e:
        reasons.append(f"{e.path or 'settings'}: {e.message}")
    if len(strategy.tendencies) > MAX_TENDENCIES:
        reasons.append(f"{len(strategy.tendencies)} tendencies; at most {MAX_TENDENCIES} reach the agent")

    if not cases:
        reasons.append("no cases to check the strategy on")
    valid = []
    for c in cases:
        ok = True
        try:
            plugin.validate_input(c["input"], path="input")
        except InputError as e:
            reasons.append(f"case {c['id']}: input: {e.path}: {e.message}")
            ok = False
        try:
            plugin.validate_output(c["expected"], path="expected")
        except InputError as e:
            reasons.append(f"case {c['id']}: expected: {e.path}: {e.message}")
            ok = False
        if ok:
            valid.append(c)

    max_turns, max_web = _limit(strategy, "max_turns"), _limit(strategy, "max_web_calls")
    prompt_chars = len(system_prompt(plugin, list(strategy.tendencies)[:MAX_TENDENCIES], plugin.web_enabled))
    input_chars = [len(json.dumps(c["input"], ensure_ascii=False, default=str)) for c in cases] or [0]
    per_call = (prompt_chars + max(input_chars)) // CHARS_PER_TOKEN
    calls = max_turns + EXTRA_CALLS
    web = max_web if plugin.web_enabled else 0
    web_tokens = web * MAX_TOOL_CHARS // CHARS_PER_TOKEN  # every allowed web result at the runner's size cap
    per_case = calls * (per_call + web_tokens)  # each call resends the conversation so far
    metrics.update({"cases": len(cases), "model_calls_per_case_max": calls, "web_calls_per_case_max": web,
                    "input_tokens_per_call_est": per_call, "input_tokens_per_case_est": per_case,
                    "limits": {k: _limit(strategy, k) for k in CORE_SETTINGS}})
    if max_model_calls_per_case is not None and calls > max_model_calls_per_case:
        reasons.append(f"up to {calls} model calls per case, over the cap of {max_model_calls_per_case}")
    if max_input_tokens_per_case is not None and per_case > max_input_tokens_per_case:
        reasons.append(f"about {per_case} input tokens per case, over the cap of {max_input_tokens_per_case}")

    hook = getattr(plugin, "gate_hook", None)
    if hook is not None and valid:
        try:
            result = hook(dict(strategy.plugin_settings), valid)
            if not isinstance(result, dict) or not isinstance(result.get("passed"), bool) \
                    or not isinstance(result.get("metrics") or {}, dict) \
                    or not isinstance(result.get("reasons") or [], list):
                raise ValueError("must return {passed: bool, metrics: dict, reasons: list}")
            metrics["plugin"] = dict(result.get("metrics") or {})
            reasons += [str(r) for r in result.get("reasons") or []]
            if not result["passed"] and not result.get("reasons"):
                reasons.append(f"{plugin.name} gate failed")
        except Exception as e:
            reasons.append(f"{plugin.name} gate failed: {type(e).__name__}: {e}")

    return {"passed": not reasons, "metrics": metrics, "reasons": reasons}
