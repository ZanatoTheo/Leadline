"""Run one input through a plugin with a set of behavioral tendencies: the agent loop.

The model sees the plugin's brief, the tendencies and the input; it may call tools; it ends with a JSON answer
`{"output": <matches the plugin's output schema>, "sources": [urls]}` (a bare output is accepted too). An answer that
doesn't parse or match the schema gets one repair try.

When any web tool is offered, the first turn must call a tool (`tool_choice="required"`), the prompt asks the agent to
search and cite, and the result warns when nothing was cited.

Providers that refuse some tool choices (the model's `tool_choices`, e.g. Anthropic's current Opus/Sonnet: auto and
none; Meta: auto only) get the closest thing: without "required", a user line asks for the search, one reminder follows
a first reply that skipped it, then a warning; without "none", the last turn and the repair are sent with no tools.
The history is append-only, and an assistant turn keeps the reply's provider-native blocks under "_raw" so they go
back unchanged (Anthropic thinking blocks are bound to the conversation that produced them)."""
import json
import re
import time
import uuid
from dataclasses import dataclass, field

from .errors import InputError, VenusError
from .tools import as_tool

MAX_TENDENCIES = 20
MAX_TOOL_CHARS = 12_000
MAX_TOOL_CALLS_PER_TURN = 8   # tool calls run from one model reply; the rest get a "skipped" answer
MAX_WEB_CALLS = 40            # web tool calls in one run
URL_RE = re.compile(r"https?://[^\s\"'<>)\]}]+")
FENCE_RE = re.compile(r"```(?:json)?\s*\n(.*?)```", re.S)


@dataclass
class RunResult:
    output: dict
    sources: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    trace: list = field(default_factory=list)
    trace_id: str = ""


def system_prompt(plugin, tendencies, web: bool) -> str:
    lines = [f"You are an agent doing this task: {plugin.brief}", ""]
    if tendencies:
        lines.append("Behavioral tendencies (follow them):")
        lines += [f"- [{t.id}] {t.text}" for t in tendencies]
        lines.append("")
    if web:
        lines += ["You must search the web before answering: call the web tools first, read what you find, and base "
                  "your answer on it. List in `sources` the URLs of the pages your answer relies on. Answers without "
                  "sources are treated as weaker.", ""]
    lines += ["The input follows this JSON Schema:", json.dumps(plugin.input_schema),
              "Your output must follow this JSON Schema:", json.dumps(plugin.output_schema), "",
              'When you are done, reply with only a JSON object: {"output": <your output>, "sources": [<urls>]}.']
    return "\n".join(lines)


def extract_json(text):
    """Return the first JSON object found in `text` (whole text, a ``` fence, or the outer braces), or None."""
    if not text:
        return None
    candidates = [text.strip(), *FENCE_RE.findall(text)]
    if "{" in text and "}" in text:
        candidates.append(text[text.index("{"): text.rindex("}") + 1])
    for c in candidates:
        try:
            value = json.loads(c)
        except ValueError:
            continue
        if isinstance(value, dict):
            return value
    return None


def parse_answer(plugin, text):
    """-> (output, sources). Raises InputError(output_invalid) with a reason the model can act on."""
    value = extract_json(text)
    if value is None:
        raise InputError("output_invalid", "no JSON object found in the answer")
    options = []
    if "output" in value:
        sources = value.get("sources") or []
        options.append((value["output"], [s for s in sources if isinstance(s, str)] if isinstance(sources, list)
                        else []))
    options.append((value, []))
    first_error = None
    for output, sources in options:
        try:
            plugin.validate_output(output, path="output")
            return output, sources
        except InputError as e:
            first_error = first_error or e
    raise first_error


def check_limits(max_turns, max_web_calls) -> None:
    """Raise ValueError (a caller's mistake, not a model failure) unless max_turns >= 1 and max_web_calls >= 0."""
    for name, value, low in (("max_turns", max_turns, 1), ("max_web_calls", max_web_calls, 0)):
        if isinstance(value, bool) or not isinstance(value, int) or value < low:
            raise ValueError(f"{name} must be a whole number >= {low}, got {value!r}")


def run_case(plugin, input, tendencies, model, tools=(), max_turns: int = 8, max_tokens: int = 1024,
             temperature=None, seed=None, clock=time.monotonic, max_web_calls: int | None = None) -> RunResult:
    """One case through the agent loop. A VenusError raised here carries `.usage`: what was spent before it failed,
    so callers can keep an honest count of calls. `max_web_calls` defaults to MAX_WEB_CALLS."""
    if max_web_calls is None:
        max_web_calls = MAX_WEB_CALLS
    check_limits(max_turns, max_web_calls)
    start = clock()
    usage = {"model_calls": 0, "input_tokens": 0, "output_tokens": 0, "web_calls": 0, "cache_hits": 0}
    try:
        return _run_case(plugin, input, tendencies, model, tools, max_turns, max_tokens, temperature, seed, clock,
                         start, usage, max_web_calls)
    except VenusError as e:
        usage["seconds"] = round(clock() - start, 3)
        e.usage = usage
        raise


def _run_case(plugin, input, tendencies, model, tools, max_turns, max_tokens, temperature, seed, clock, start,
              usage, max_web_calls) -> RunResult:
    tools = [as_tool(t) for t in tools]
    by_name = {}
    for t in tools:
        if t.name in by_name:
            raise VenusError("tool_name_duplicate", f"two tools are named {t.name!r}")
        by_name[t.name] = t
    specs = [t.spec() for t in tools] or None
    web = any(t.web for t in tools)

    warnings = []
    tendencies = list(tendencies)
    if len(tendencies) > MAX_TENDENCIES:
        warnings.append(f"{len(tendencies)} tendencies given; only the first {MAX_TENDENCIES} were used")
        tendencies = tendencies[:MAX_TENDENCIES]

    messages = [{"role": "system", "content": system_prompt(plugin, tendencies, web)},
                {"role": "user", "content": "Input:\n" + json.dumps(input, ensure_ascii=False)}]
    trace, seen_urls = [], set()
    skipped = 0
    choices = set(getattr(model, "tool_choices", None) or ("auto", "required", "none"))
    can_force, can_none = "required" in choices, "none" in choices

    def call(tool_choice, turn, offer_tools=True):
        reply = model.chat(messages, tools=specs if offer_tools else None, tool_choice=tool_choice,
                           max_tokens=max_tokens, temperature=temperature, seed=seed)
        if getattr(reply, "cached", False):
            usage["cache_hits"] += 1  # no call was made: it is not a model call and has no tokens
        else:
            usage["model_calls"] += 1
            usage["input_tokens"] += reply.usage.get("input_tokens", 0)
            usage["output_tokens"] += reply.usage.get("output_tokens", 0)
        trace.append({"type": "model", "turn": turn, "tool_choice": tool_choice,
                      "tool_calls": [c.name for c in reply.tool_calls], "text": (reply.text or "")[:500],
                      "usage": dict(reply.usage)})
        return reply

    ask_to_search = web and not can_force and max_turns > 1
    if ask_to_search:
        web_names = ", ".join(t.name for t in tools if t.web)
        messages.append({"role": "user", "content": f"Start by calling a web tool ({web_names}) to search; answer "
                                                    "only after reading the results."})

    reply = None
    for turn in range(max_turns):
        offer = True
        if not specs:
            tool_choice = None
        elif turn == max_turns - 1:  # the last turn wins over the forced first search, so max_turns=1 still answers
            messages.append({"role": "user", "content": "No more tool calls. Give your final JSON answer now."})
            if turn > 0:  # only when tool turns were actually cut short
                warnings.append(f"turn limit ({max_turns}) reached; the final answer was asked for without more tools")
            tool_choice, offer = ("none", True) if can_none else (None, False)
        elif turn == 0 and web:
            tool_choice = "required" if can_force else "auto"
        else:
            tool_choice = "auto"
        reply = call(tool_choice, turn, offer)
        if turn == 0 and ask_to_search and tool_choice == "auto" and not reply.tool_calls:
            messages.append(_assistant_message(reply))
            messages.append({"role": "user", "content": "You have not searched yet. Call a web tool now, before "
                                                        "answering."})
            reply = call("auto", "0-reminder")
            if not reply.tool_calls:
                warnings.append("no forced search: provider supports auto only, and the model answered without "
                                "searching")
        if not reply.tool_calls or tool_choice == "none" or not offer:
            break
        messages.append(_assistant_message(reply))
        for i, c in enumerate(reply.tool_calls):
            if i >= MAX_TOOL_CALLS_PER_TURN:
                content = json.dumps({"error": f"skipped: at most {MAX_TOOL_CALLS_PER_TURN} tool calls per reply"})
                trace.append({"type": "tool", "name": c.name, "arguments": c.arguments, "ok": False,
                              "chars": len(content), "skipped": True})
                skipped += 1
            else:
                content = _run_tool(by_name, c, usage, trace, max_web_calls)
            seen_urls.update(URL_RE.findall(content))
            messages.append({"role": "tool", "tool_call_id": c.id, "content": content})

    if skipped:
        warnings.append(f"{skipped} tool call(s) skipped: more than {MAX_TOOL_CALLS_PER_TURN} in one reply")
    refused = sum(1 for t in trace if t.get("capped"))
    if refused:
        warnings.append(f"web call limit ({max_web_calls}) reached; {refused} web call(s) refused")

    # A caching model keeps a bad answer while the repair is tried: when the repair works, both stay stored, so a
    # rerun replays the same two replies instead of asking a non-deterministic model again at the bad slot (that
    # sent the phase 9 rerun down another path). When the repair fails too, both are dropped and asked again later.
    discard = getattr(model, "discard", None)
    try:
        output, sources = parse_answer(plugin, reply.text if reply else None)
    except InputError as e:
        bad_key = getattr(model, "last_key", None) if reply else None
        trace.append({"type": "invalid_answer", "path": e.path, "error": e.message})
        messages.append(_answer_message(reply) if reply else {"role": "assistant", "content": ""})
        messages.append({"role": "user", "content": f"Your answer was not valid: {e.path or 'answer'}: {e.message}. "
                                                    "Reply again with only the corrected JSON object."})
        if not specs:
            reply = call(None, "repair")
        elif can_none:
            reply = call("none", "repair")
        else:
            reply = call(None, "repair", offer_tools=False)
        try:
            output, sources = parse_answer(plugin, reply.text)
        except InputError:
            if discard:
                discard(getattr(model, "last_key", None))  # the failed repair
                discard(bad_key)  # and the bad answer it was meant to fix
            raise
        warnings.append(f"the first answer was invalid ({e.path or 'answer'}: {e.message}) and was repaired")

    if web and not sources:
        warnings.append("web search was on but the answer did not cite any source URLs")
    unseen = [s for s in sources if s not in seen_urls]
    if web and unseen:
        warnings.append(f"{len(unseen)} cited URL(s) never appeared in tool results")
    usage["seconds"] = round(clock() - start, 3)
    return RunResult(output=output, sources=sources, warnings=warnings, usage=usage, trace=trace,
                     trace_id=uuid.uuid4().hex)


def _assistant_message(reply) -> dict:
    """The assistant turn to append: text, tool calls in OpenAI form, and the provider's own blocks under "_raw"."""
    message = {"role": "assistant", "content": reply.text if reply.tool_calls else (reply.text or "")}
    if reply.tool_calls:
        message["tool_calls"] = [{"id": c.id, "type": "function",
                                  "function": {"name": c.name, "arguments": json.dumps(c.arguments or {})}}
                                 for c in reply.tool_calls]
    if getattr(reply, "raw", None) is not None:
        message["_raw"] = reply.raw
    return message


def _answer_message(reply) -> dict:
    """The assistant turn before a repair. Tool calls in that reply were never run, so they are left out (a tool call
    with no tool result after it is refused by Anthropic). Provider blocks are kept only if text remains."""
    if not reply.tool_calls:
        return _assistant_message(reply)
    message = {"role": "assistant", "content": reply.text or "(no answer)"}
    raw = [b for b in (getattr(reply, "raw", None) or []) if b.get("type") not in ("tool_use", "server_tool_use")]
    if any(b.get("type") == "text" for b in raw):
        message["_raw"] = raw
    return message


def _run_tool(by_name, call, usage, trace, max_web_calls) -> str:
    tool = by_name.get(call.name)
    capped = False
    if tool is None:
        result, ok = {"error": f"unknown tool {call.name!r}; available: {sorted(by_name)}"}, False
    elif call.parse_error:
        result, ok = {"error": f"could not read your arguments: {call.parse_error}"}, False
    elif tool.web and usage["web_calls"] >= max_web_calls:
        result, ok = {"error": f"web call limit reached ({max_web_calls} per run); answer with what you have"}, False
        capped = True
    else:
        if tool.web:
            usage["web_calls"] += 1
        try:
            result, ok = tool.fn(call.arguments or {}), True
        except Exception as e:  # a tool failure is information for the agent, not a crash
            result, ok = {"error": f"{call.name} failed: {type(e).__name__}: {e}"}, False
    content = json.dumps(result, ensure_ascii=False, default=str)
    if len(content) > MAX_TOOL_CHARS:
        content = content[:MAX_TOOL_CHARS] + "... [truncated]"
    entry = {"type": "tool", "name": call.name, "arguments": call.arguments, "ok": ok, "chars": len(content)}
    if capped:
        entry["capped"] = True
    trace.append(entry)
    return content
