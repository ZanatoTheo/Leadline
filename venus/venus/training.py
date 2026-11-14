"""Training intake: run validated cases and score them against `expected`.

1. Research step (when web tools are available and the plugin allows them): the agent searches the web on the
   plugin's brief and drafts the first behavioral tendencies, each citing its URLs. They are saved, with the plugin's
   seed tendencies, as a `draft` strategy (`strategies/<plugin>-draft-<timestamp>.json`). Never `validated`: promoting
   a strategy is a separate, deliberate step.
2. Each case runs through `run_case` with those tendencies; the plugin's checker scores the output against
   `expected`. One failing case marks only that case; the overall status becomes `partial`.
3. Records go to `runs/<trace_id>/training.jsonl` when `runs_dir` is given."""
import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

from .errors import VenusError
from .plugin import _validate
from .request import VENUS_VERSION
from .runner import check_limits, run_case
from .schemas import load_schema
from .tendency import Tendency
from .tools import as_tool, collect_tools

RESEARCH_MARK = "[venus:research]"
MAX_RESEARCHED = 5
RESEARCH_MAX_TOKENS = 8000
USAGE_KEYS = ("model_calls", "input_tokens", "output_tokens", "web_calls", "cache_hits")
TRAIN_CASE_LIMITS = {"max_turns": 5, "max_web_calls": 6}  # per training case; tighter than a served run


@dataclass(frozen=True)
class ResearchTask:
    """Looks enough like a Plugin for `run_case`: the research step is an agent run with its own output schema."""
    name: str
    brief: str
    input_schema: dict
    output_schema: dict

    def validate_output(self, value, path="output", code="output_invalid"):
        _validate(self.output_schema, value, path, code)


def research_task(plugin, n: int = MAX_RESEARCHED) -> ResearchTask:
    return ResearchTask(
        name=f"{plugin.name}-research",
        brief=(f"{RESEARCH_MARK} Research on the web how to do the task below well. Then write up to {n} behavioral "
               "tendencies: short, concrete instructions that an agent doing the task should follow. Each tendency "
               f"must list the URLs it is based on. Write at most {n} tendencies and keep each one under 400 "
               "characters.\nTask: " + plugin.brief),
        input_schema={"type": "object"},
        output_schema={"type": "object", "required": ["tendencies"], "properties": {"tendencies": {
            "type": "array", "minItems": 1, "maxItems": n, "items": {
                "type": "object", "required": ["text", "sources"], "properties": {
                    "text": {"type": "string", "minLength": 5, "maxLength": 400},
                    "sources": {"type": "array", "items": {"type": "string", "pattern": "^https?://"}}}}}}},
    )


def research(plugin, cases, model, web_tools, n: int = MAX_RESEARCHED):
    """-> (tendencies, RunResult). Raises VenusError if the agent can't produce valid tendencies."""
    task = research_task(plugin, n)
    task_input = {"task": plugin.brief, "task_output_schema": plugin.output_schema,
                  "example_inputs": [c.input for c in list(cases)[:3]]}
    # Room for n tendencies of up to 400 characters each plus their URLs: at 1024 tokens the answer could be cut off,
    # fail validation and need a repair call.
    result = run_case(task, task_input, [], model, tools=web_tools, max_turns=6, max_tokens=RESEARCH_MAX_TOKENS)
    tendencies = [Tendency(id=f"research-{i + 1}", text=t["text"].strip(), sources=tuple(t.get("sources", [])))
                  for i, t in enumerate(result.output["tendencies"])]
    return tendencies, result


def save_draft(strategies_dir, plugin, base_model: dict, tendencies, now: datetime, notes: str) -> str:
    folder = Path(strategies_dir)
    folder.mkdir(parents=True, exist_ok=True)
    base_id = f"{plugin.name[:40]}-draft-{now.strftime('%Y%m%dT%H%M%S')}"
    strategy_id, n = base_id, 1
    while (folder / f"{strategy_id}.json").exists():
        n += 1
        strategy_id = f"{base_id}-{n}"
    data = {"id": strategy_id, "plugin": plugin.name, "plugin_version": plugin.version, "status": "draft",
            "base_model": dict(base_model), "tendencies": [t.to_dict() for t in tendencies],
            "created_at": now.isoformat(timespec="seconds"), "notes": notes}
    errors = list(Draft202012Validator(load_schema("strategy")).iter_errors(data))
    if errors:
        raise VenusError("strategy_invalid", f"draft strategy would be invalid: {errors[0].message}")
    (folder / f"{strategy_id}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return strategy_id


def train(request, model, web_tools=(), strategies_dir=None, runs_dir=None, base_model=None,
          max_researched: int = MAX_RESEARCHED, now=None, clock=time.monotonic, case_limits: dict | None = None) -> dict:
    """`case_limits` overrides TRAIN_CASE_LIMITS (`max_turns`, `max_web_calls`) for each case."""
    unknown = set(case_limits or {}) - set(TRAIN_CASE_LIMITS)
    if unknown:
        raise ValueError(f"unknown case_limits {sorted(unknown)}; known: {sorted(TRAIN_CASE_LIMITS)}")
    limits = {**TRAIN_CASE_LIMITS, **(case_limits or {})}
    check_limits(limits["max_turns"], limits["max_web_calls"])
    start = clock()
    plugin = request.plugin
    trace_id = uuid.uuid4().hex
    usage = dict.fromkeys(USAGE_KEYS, 0)
    warnings, records = [], []
    tendencies = list(plugin.seed_tendencies)
    web = [t for t in map(as_tool, web_tools) if not t.run_only] if plugin.web_enabled else []  # never run-only
    draft_id = None

    def add_usage(u):
        for k in USAGE_KEYS:
            usage[k] += u.get(k, 0)

    if not plugin.web_enabled:
        warnings.append("research skipped: the plugin turns web tools off")
    elif not web:
        warnings.append("research skipped: no web tools available (set CONTEXT_DEV_API_KEY)")
    else:
        try:
            found, res = research(plugin, request.cases, model, web, max_researched)
            add_usage(res.usage)
            warnings += [f"research: {w}" for w in res.warnings]
            tendencies += found
            if strategies_dir is not None:
                draft_id = save_draft(strategies_dir, plugin, base_model or {"model": "nemotron"}, tendencies,
                                      now or datetime.now(timezone.utc),
                                      "Drafted by the training research step from web search. Not validated.")
            else:
                warnings.append("research done but the draft was not saved: no strategies folder given")
            records.append({"type": "research", "tendencies": [t.to_dict() for t in found], "trace": res.trace})
        except VenusError as e:
            add_usage(getattr(e, "usage", None) or {})  # calls made before the failure still count
            warnings.append(f"research failed: {e.code}: {e.message}")

    outputs, scores, first_error = [], [], None
    for case in request.cases:
        record = {"type": "case", "case_id": case.id, "input": case.input, "expected": case.expected,
                  "tendencies": [t.id for t in tendencies]}
        result = None
        try:
            tools = collect_tools(plugin, case.input, web, mode="train")
            result = run_case(plugin, case.input, tendencies, model, tools=tools, **limits)
            add_usage(result.usage)
            score = plugin.check(case.input, result.output, case.expected)
        except VenusError as e:
            first_error = first_error or e
            if result is None:
                add_usage(getattr(e, "usage", None) or {})  # the run failed; what it spent still counts
            # else the run finished and its usage was added; only scoring failed
            outputs.append({"case_id": case.id, "output": result.output if result else None, "status": "error",
                            "error": e.to_dict()})
            record.update(status="error", error=e.to_dict(), output=result.output if result else None)
            records.append(record)
            continue
        outputs.append({"case_id": case.id, "output": result.output, "sources": result.sources, "status": "ok"})
        scores.append({"case_id": case.id, **score.to_dict()})
        warnings += [f"case {case.id}: {w}" for w in result.warnings]
        record.update(status="ok", output=result.output, sources=result.sources, score=score.to_dict(),
                      usage=result.usage, trace=result.trace)
        records.append(record)

    failed = sum(1 for o in outputs if o["status"] == "error")
    status = "ok" if failed == 0 else ("error" if failed == len(outputs) else "partial")
    usage["seconds"] = round(clock() - start, 3)
    response = {"venus_version": VENUS_VERSION, "plugin": plugin.name, "mode": "training", "status": status,
                "outputs": outputs, "scores": scores, "trace_id": trace_id, "usage": usage, "warnings": warnings}
    if draft_id:
        response["draft_strategy"] = draft_id
    if status == "error":
        response["error"] = {"code": "all_cases_failed",
                             "message": f"all {failed} cases failed; first: {first_error.code}: {first_error.message}"}

    if runs_dir is not None:
        folder = Path(runs_dir) / trace_id
        folder.mkdir(parents=True, exist_ok=True)
        with open(folder / "training.jsonl", "w") as f:
            for r in records:
                if r["type"] == "case":
                    f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
        research_records = [r for r in records if r["type"] == "research"]
        if research_records:
            (folder / "research.json").write_text(json.dumps(research_records[0], indent=2, default=str))
    return response
