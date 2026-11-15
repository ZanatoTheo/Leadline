"""Model calls through Anthropic's Messages API, with the same `chat(...) -> ModelReply` door as `ModelClient`.

Venus keeps its history in OpenAI chat form; this module converts it on the way out (system prompt apart, tool calls
as `tool_use` blocks, a turn's tool results in one user message, tools with `input_schema`) and converts replies back.
An assistant turn that carries the reply's own blocks under "_raw" is sent back exactly as received: Anthropic thinking
blocks are bound to the conversation that produced them, so the history must stay append-only.

Requests use adaptive thinking (always on for current Opus models; `effort` sets its depth), the server-side refusal
fallback (`fallbacks: "default"`), automatic prompt caching, and never `temperature`/`seed` (current API versions
refuse them). Thinking shares `max_tokens`, so a floor (VENUS_CLAUDE_MIN_TOKENS, default 16000) keeps answers from
being cut off. Retries, budget and rate limits follow `models.call_with_retries`."""
import os
import time

import anthropic

from .budget import Budget
from .config import ModelSpec
from .errors import ModelError
from .models import DEFAULT_ATTEMPTS, ModelReply, ToolCall, api_key_for, call_with_retries, parse_arguments, \
    shared_limiter, _short

BETAS = ["server-side-fallback-2026-07-01"]
DEFAULT_EFFORT = "medium"
MIN_TOKENS = 16000
DEFAULT_TIMEOUT = 300.0  # thinking turns can run minutes; VENUS_MODEL_TIMEOUT overrides
STOP_REASONS = {"end_turn": "stop", "tool_use": "tool_calls", "max_tokens": "length", "stop_sequence": "stop"}
# Blocks a fallback makes stale when they come before the switch point (they were the declining model's).
STALE_BEFORE_FALLBACK = {"thinking", "redacted_thinking", "tool_use"}


class AnthropicClient:
    def __init__(self, spec: ModelSpec, budget: Budget | None = None, http_client=None, sleep=time.sleep,
                 max_attempts: int = DEFAULT_ATTEMPTS, api_key: str | None = None, environ=None,
                 timeout: float | None = None, limiter="shared"):
        environ = os.environ if environ is None else environ
        api_key = api_key_for(spec, api_key, environ)
        self.spec = spec
        self.budget = budget
        self.sleep = sleep
        self.max_attempts = max_attempts
        self.tool_choices = tuple(spec.tool_choices)
        self.effort = environ.get("VENUS_CLAUDE_EFFORT") or DEFAULT_EFFORT
        self.min_tokens = _positive_int(environ.get("VENUS_CLAUDE_MIN_TOKENS"), MIN_TOKENS)
        # settings that change replies but are not chat() args; CachedModel puts them in its key
        self.cache_tag = {"effort": self.effort, "min_tokens": self.min_tokens, "fallbacks": "default", "betas": BETAS}
        if timeout is None:
            timeout = _positive_float(environ.get("VENUS_MODEL_TIMEOUT"), DEFAULT_TIMEOUT)
        self.limiter = shared_limiter(spec.provider, spec.base_url, spec.key_env) if limiter == "shared" else limiter
        self._client = anthropic.Anthropic(api_key=api_key, base_url=spec.base_url, max_retries=0, timeout=timeout,
                                           http_client=http_client)

    def chat(self, messages, tools=None, tool_choice=None, max_tokens=1024, temperature=None, seed=None) -> ModelReply:
        if self.budget is not None:
            self.budget.check()
        system, converted = to_anthropic_messages(messages)
        params = {"model": self.spec.model, "max_tokens": max(max_tokens, self.min_tokens), "messages": converted,
                  "thinking": {"type": "adaptive"}, "output_config": {"effort": self.effort},
                  "cache_control": {"type": "ephemeral"}, "fallbacks": "default", "betas": BETAS}
        if system:
            params["system"] = system
        if tools:
            params["tools"] = [to_anthropic_tool(t) for t in tools]
        if tool_choice is not None:
            params["tool_choice"] = to_anthropic_tool_choice(tool_choice)
        # temperature and seed are deliberately not sent: current Anthropic API versions refuse them.

        response = call_with_retries(self, lambda: self._client.beta.messages.create(**params),
                                     anthropic.APIStatusError, anthropic.APIConnectionError, anthropic.APIError)
        reply = parse_response(response)
        if self.budget is not None:
            self.budget.charge(reply.usage["input_tokens"], reply.usage["output_tokens"])
        return reply


EMPTY = "(empty)"


def to_anthropic_tool(tool: dict) -> dict:
    fn = tool.get("function", tool)
    out = {"name": fn["name"], "input_schema": fn.get("parameters") or {"type": "object", "properties": {}}}
    if fn.get("description"):
        out["description"] = fn["description"]
    return out


def to_anthropic_tool_choice(choice):
    if choice == "auto":
        return {"type": "auto"}
    if choice == "none":
        return {"type": "none"}
    if isinstance(choice, dict) and isinstance(choice.get("name"), str):
        return {"type": "tool", "name": choice["name"]}
    raise ModelError("model_bad_request", f"tool_choice {choice!r} is not supported by the Anthropic client "
                                          "(current models refuse forced tool use; use auto or none)")


def to_anthropic_messages(messages) -> tuple[str | None, list]:
    """Venus (OpenAI-style) messages -> (system text, Anthropic messages). Consecutive same-role turns are merged."""
    system = None
    out = []

    def add(role, blocks):
        if out and out[-1]["role"] == role:
            prev = out[-1]["content"]
            if isinstance(prev, str):
                prev = [{"type": "text", "text": prev}]
            out[-1]["content"] = prev + blocks
        else:
            out.append({"role": role, "content": blocks})

    for i, m in enumerate(messages):
        role, content = m.get("role"), m.get("content")
        if role == "system" and i == 0:
            system = content
        elif role == "system" or role == "user":  # a later system line is passed as user text
            text = content if isinstance(content, str) else str(content or "")
            text = text or EMPTY  # the API refuses empty text
            if out and out[-1]["role"] == "user":
                add("user", [{"type": "text", "text": text}])
            else:
                out.append({"role": "user", "content": text})
        elif role == "tool":
            add("user", [{"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": content or EMPTY}])
        elif role == "assistant":
            raw = m.get("_raw")
            if isinstance(raw, list) and raw:
                out.append({"role": "assistant", "content": raw})
                continue
            blocks = [{"type": "text", "text": content}] if content else []
            for tc in m.get("tool_calls") or []:
                fn = tc.get("function", {})
                args, _ = parse_arguments(fn.get("arguments"))
                blocks.append({"type": "tool_use", "id": tc["id"], "name": fn.get("name"), "input": args or {}})
            add("assistant", blocks or [{"type": "text", "text": "(no answer)"}])
    return system, out


def parse_response(response) -> ModelReply:
    stop = getattr(response, "stop_reason", None)
    if stop == "refusal":
        details = getattr(response, "stop_details", None)
        category = getattr(details, "category", None) if details is not None else None
        raise ModelError("model_bad_reply", f"the model declined the request (refusal, category {category!r})")
    blocks = [_block_dict(b) for b in (getattr(response, "content", None) or [])]
    last_fallback = max((i for i, b in enumerate(blocks) if b.get("type") == "fallback"), default=-1)
    raw = [b for i, b in enumerate(blocks) if not (i < last_fallback and b.get("type") in STALE_BEFORE_FALLBACK)]
    texts = [b["text"] for b in raw if b.get("type") == "text" and b.get("text")]
    calls = []
    for b in raw:
        if b.get("type") == "tool_use":
            args, error = parse_arguments(b.get("input"))
            calls.append(ToolCall(id=b.get("id") or f"toolu_{len(calls)}", name=b.get("name"), arguments=args,
                                  parse_error=error))
    usage = getattr(response, "usage", None)
    input_tokens = sum((getattr(usage, k, 0) or 0) for k in
                       ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
    return ModelReply(text="\n".join(texts) if texts else None, tool_calls=calls,
                      usage={"input_tokens": input_tokens, "output_tokens": getattr(usage, "output_tokens", 0) or 0},
                      model=getattr(response, "model", None), finish_reason=STOP_REASONS.get(stop, stop), raw=raw)


def _block_dict(block) -> dict:
    if isinstance(block, dict):
        return block
    try:
        return block.model_dump(mode="json", by_alias=True, exclude_none=True)
    except AttributeError as e:
        raise ModelError("model_bad_reply", f"unreadable content block: {_short(repr(block))}") from e


def _positive_int(value, default):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _positive_float(value, default):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default
