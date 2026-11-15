"""The one door for model calls: OpenAI-style Chat Completions (Verda, NVIDIA Build), with tools, retries and budget.

The SDK's own retries are off (`max_retries=0`); this module retries 408/409/429/5xx, timeouts and connection errors
with exponential backoff, and fails fast on auth and bad-request errors."""
import json
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field

import openai

from .budget import Budget
from .config import PROVIDERS, ModelSpec
from .errors import ModelError

RETRY_STATUS = {408, 409, 429}
AUTH_STATUS = {401, 403}
TOOL_CHOICES = {"auto", "required", "none"}
DEFAULT_ATTEMPTS = 3
MAX_RATE_WAIT = 90.0  # seconds one request may wait for a free slot before giving up


class RateLimiter:
    """At most `rpm` requests in any `window` seconds (default 61: one minute plus a second of margin, in case the
    provider's clock runs ahead). `acquire()` waits for a free slot and raises `model_unavailable` rather than wait
    more than `max_wait` seconds in all, time spent queued behind other threads included."""

    def __init__(self, rpm: int, clock=time.monotonic, sleep=time.sleep, max_wait: float = MAX_RATE_WAIT,
                 window: float = 61.0):
        if not isinstance(rpm, int) or rpm < 1:
            raise ValueError(f"rpm must be a whole number >= 1, got {rpm!r}")
        self.rpm = rpm
        self.clock = clock
        self.sleep = sleep
        self.max_wait = max_wait
        self.window = window
        self._stamps = deque()
        self._lock = threading.Lock()

    def acquire(self, max_wait: float | None = None) -> None:
        """`max_wait` lowers the cap for this call (e.g. to what is left of a request's time budget)."""
        cap = self.max_wait if max_wait is None else min(self.max_wait, max_wait)
        start = self.clock()
        if not self._lock.acquire(timeout=max(cap, 0)):  # one waiter at a time, so slots go out in order
            raise self._full(cap)
        try:
            while True:
                now = self.clock()
                while self._stamps and now - self._stamps[0] >= self.window:
                    self._stamps.popleft()
                if len(self._stamps) < self.rpm:
                    self._stamps.append(now)
                    return
                wait = self._stamps[0] + self.window - now
                if now - start + wait > cap:
                    raise self._full(cap)
                self.sleep(wait)
        finally:
            self._lock.release()

    def _full(self, cap) -> ModelError:
        return ModelError("model_unavailable", f"rate limit of {self.rpm} requests/min: no free slot within {cap:g}s")


_shared_limiters: dict = {}
_shared_lock = threading.Lock()


def shared_limiter(provider: str, base_url: str | None = None, key_env: str | None = None) -> RateLimiter | None:
    """One limiter per provider endpoint and key (clients come and go per request), or None when it has no limit."""
    rpm = (PROVIDERS.get(provider) or {}).get("rpm")
    if not rpm:
        return None
    ident = (provider, base_url, key_env)
    with _shared_lock:
        if ident not in _shared_limiters:
            _shared_limiters[ident] = RateLimiter(rpm)
        return _shared_limiters[ident]


def function_tool(name: str, description: str, parameters: dict) -> dict:
    """A tool in OpenAI function-tool format."""
    return {"type": "function", "function": {"name": name, "description": description, "parameters": parameters}}


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict | None
    parse_error: str | None = None


@dataclass(frozen=True)
class ModelReply:
    text: str | None
    tool_calls: list = field(default_factory=list)
    usage: dict = field(default_factory=lambda: {"input_tokens": 0, "output_tokens": 0})
    model: str | None = None
    finish_reason: str | None = None
    cached: bool = False  # True when the reply came from the disk cache: no call, no cost
    # Provider-native content blocks (Anthropic: thinking, text, tool_use, ...), to be sent back unchanged in the next
    # request of the same run. The runner stores them under the assistant message's "_raw" key; None for providers
    # whose replies are fully described by text + tool_calls.
    raw: list | None = None


def parse_arguments(raw) -> tuple[dict | None, str | None]:
    """Tool-call arguments -> (dict, None) or (None, reason). Never raises."""
    if isinstance(raw, dict):
        return raw, None
    try:
        value = json.loads(raw or "{}")
    except (TypeError, ValueError) as e:
        return None, f"arguments are not valid JSON: {e}"
    if not isinstance(value, dict):
        return None, f"arguments must be a JSON object, got {type(value).__name__}"
    return value, None


def tool_choice_param(tool_choice):
    if tool_choice is None or (isinstance(tool_choice, str) and tool_choice in TOOL_CHOICES):
        return tool_choice
    if isinstance(tool_choice, dict) and isinstance(tool_choice.get("name"), str):
        return {"type": "function", "function": {"name": tool_choice["name"]}}
    raise ModelError("model_bad_request", f"tool_choice must be auto, required, none or {{'name': ...}}, "
                                          f"got {tool_choice!r}")


def api_key_for(spec: ModelSpec, api_key: str | None, environ) -> str:
    """The key: given, or from the spec's variable, or the provider's second name for it. Raises when none is set."""
    alt = (PROVIDERS.get(spec.provider) or {}).get("key_env_alt")
    key = api_key or environ.get(spec.key_env) or (environ.get(alt) if alt else None)
    if not key:
        raise ModelError("model_config_missing", f"no API key: set {spec.key_env} (e.g. in .env)")
    return key


def strip_internal(messages) -> list:
    """Messages without Venus's own keys (those starting with "_", e.g. "_raw"), which no provider accepts."""
    return [{k: v for k, v in m.items() if not k.startswith("_")} if isinstance(m, dict) else m for m in messages]


def call_with_retries(owner, send, status_error, connection_error, other_error=None):
    """Run `send()` with the owner's retry policy: rate limiter slot before each attempt, budget recheck before a
    retry, 408/409/429/5xx and connection errors retried with backoff, auth (401/403) and other 4xx raised at once.
    `owner` has spec, budget, limiter, sleep and max_attempts; the error classes are the SDK's. `other_error` (the SDK's
    base error) catches the rest, e.g. a reply that fails the SDK's own validation, as `model_bad_reply` at once."""
    last = None
    for attempt in range(owner.max_attempts):
        if attempt > 0 and owner.budget is not None:
            owner.budget.check()  # backoff and retries spend time; stop when the budget is gone
        if owner.limiter is not None:  # every attempt is a request the provider counts
            left = None
            if owner.budget is not None and owner.budget.max_seconds is not None:
                left = owner.budget.max_seconds - owner.budget.seconds()  # never wait past the request's budget
            owner.limiter.acquire(max_wait=left)
        try:
            return send()
        except status_error as e:
            status = e.status_code
            if status in AUTH_STATUS:
                raise ModelError("model_auth_failed", f"{owner.spec.provider} rejected the key ({status})") from e
            if status not in RETRY_STATUS and status < 500:
                raise ModelError("model_bad_request", f"{owner.spec.provider} returned {status}: "
                                                      f"{_short(e.message)}") from e
            last = f"HTTP {status}: {_short(e.message)}"
        except connection_error as e:  # includes timeouts
            last = f"{type(e).__name__}: {_short(str(e))}"
        except Exception as e:
            if other_error is None or not isinstance(e, other_error):
                raise
            raise ModelError("model_bad_reply", f"{owner.spec.provider} {owner.spec.model}: "
                                                f"{type(e).__name__}: {_short(str(e))}") from e
        if attempt + 1 < owner.max_attempts:
            owner.sleep(min(2 ** attempt, 30))
    raise ModelError("model_unavailable",
                     f"{owner.spec.provider} {owner.spec.model}: gave up after {owner.max_attempts} tries ({last})")


class ModelClient:
    def __init__(self, spec: ModelSpec, budget: Budget | None = None, http_client=None, sleep=time.sleep,
                 max_attempts: int = DEFAULT_ATTEMPTS, api_key: str | None = None, environ=None,
                 timeout: float | None = None, limiter="shared"):
        environ = os.environ if environ is None else environ
        api_key = api_key_for(spec, api_key, environ)
        if timeout is None:  # an explicit `timeout` from the caller wins; the env value has a floor for Verda
            timeout = _timeout_from(environ)
            if spec.provider == "verda":
                timeout = max(timeout, VERDA_MIN_TIMEOUT)  # a cold container takes over 60 s to answer
        self.timeout = timeout
        self.spec = spec
        self.budget = budget
        self.sleep = sleep
        self.max_attempts = max_attempts
        self.tool_choices = tuple(spec.tool_choices)  # the runner adapts when "required" or "none" is missing
        # "shared" = the provider's shared limiter (None when it has no limit); or pass a RateLimiter, or None.
        self.limiter = shared_limiter(spec.provider, spec.base_url, spec.key_env) if limiter == "shared" else limiter
        self._client = openai.OpenAI(base_url=spec.base_url, api_key=api_key, max_retries=0, timeout=timeout,
                                     http_client=http_client)

    def chat(self, messages, tools=None, tool_choice=None, max_tokens=1024, temperature=None, seed=None) -> ModelReply:
        if self.budget is not None:
            self.budget.check()
        params = {"model": self.spec.model, "messages": strip_internal(messages), "max_tokens": max_tokens}
        if tools:
            params["tools"] = tools
        if tool_choice is not None:
            params["tool_choice"] = tool_choice_param(tool_choice)
        if temperature is not None:
            params["temperature"] = temperature
        if seed is not None:
            params["seed"] = seed

        completion = self._call(params)
        reply = self._parse(completion)
        if self.budget is not None:
            self.budget.charge(reply.usage["input_tokens"], reply.usage["output_tokens"])
        return reply

    def _call(self, params):
        return call_with_retries(self, lambda: self._client.chat.completions.create(**params),
                                 openai.APIStatusError, openai.APIConnectionError, openai.APIError)

    def _parse(self, completion) -> ModelReply:
        try:
            choice = completion.choices[0]
            message = choice.message
        except (AttributeError, IndexError, TypeError) as e:
            raise ModelError("model_bad_reply", f"reply has no choices: {_short(str(completion))}") from e
        calls = []
        for i, tc in enumerate(message.tool_calls or []):
            fn = getattr(tc, "function", None)
            if fn is None:
                continue
            args, error = parse_arguments(fn.arguments)
            calls.append(ToolCall(id=tc.id or f"call_{i}", name=fn.name, arguments=args, parse_error=error))
        if choice.finish_reason == "length" and not calls and not (message.content or "").strip():
            # Reasoning models (Nemotron: `reasoning_content`) can spend the whole budget thinking. The reasoning
            # itself is never kept or sent back; only `content` counts.
            raise ModelError("model_bad_reply", "the reply was cut off by the max_tokens limit before any answer "
                                                "(the model may have used it all for reasoning); raise max_tokens")
        usage = completion.usage
        return ModelReply(
            text=message.content,
            tool_calls=calls,
            usage={"input_tokens": getattr(usage, "prompt_tokens", 0) or 0,
                   "output_tokens": getattr(usage, "completion_tokens", 0) or 0},
            model=completion.model,
            finish_reason=choice.finish_reason,
        )


class CachedModel:
    """Puts a disk cache of replies in front of a model client (or FakeModel). Same `.chat(...)` signature.

    Only repeatable requests are cached: with a `seed`, or `temperature == 0`. When the caller gives neither, this
    wrapper asks for `temperature=0` so the request can be cached. Temperature above 0 without a seed goes straight to
    the model. A hit makes no call, so the inner budget is not charged and the reply's usage is zero. Replies that look
    wrong (bad tool-call arguments, cut off by the token limit, empty) are never stored."""

    def __init__(self, inner, cache, provider: str | None = None, model: str | None = None):
        spec = getattr(inner, "spec", None)
        self.inner = inner
        self.cache = cache
        self.spec = spec
        self.provider = provider or getattr(spec, "provider", None)
        self.model = model or getattr(spec, "model", None)
        self.base_url = getattr(spec, "base_url", None)  # another endpoint may serve another model under one name
        self.budget = getattr(inner, "budget", None)
        self.tool_choices = getattr(inner, "tool_choices", None)
        self.cache_tag = getattr(inner, "cache_tag", None)
        self._last_key = None

    @property
    def last_key(self) -> str | None:
        """The cache key of the last `chat` call (None for an uncached request)."""
        return self._last_key

    def discard(self, key: str | None) -> None:
        """Forget one stored reply by its key (from `last_key`)."""
        if key is not None:
            self.cache.delete(key)
            if key == self._last_key:
                self._last_key = None

    def discard_last(self) -> None:
        """Forget the reply of the last `chat` call, e.g. when its answer failed validation, so it is asked again."""
        self.discard(self._last_key)

    def chat(self, messages, tools=None, tool_choice=None, max_tokens=1024, temperature=None, seed=None) -> ModelReply:
        self._last_key = None
        if temperature is None and seed is None:
            temperature = 0
        args = dict(tools=tools, tool_choice=tool_choice, max_tokens=max_tokens, temperature=temperature, seed=seed)
        random = isinstance(temperature, (int, float)) and temperature > 0 and seed is None
        if random:
            return self.inner.chat(messages, **args)
        parts = [self.provider, self.base_url, self.model, messages, tools, tool_choice, max_tokens, temperature, seed]
        if self.cache_tag:  # settings outside the request args that change replies (e.g. Anthropic effort)
            parts.append(self.cache_tag)
        key = self.cache.key("model-reply", *parts)
        self._last_key = key
        hit = _reply_from_entry(self.cache.get(key))
        if hit is not None:
            return hit
        reply = self.inner.chat(messages, **args)
        if _cacheable(reply):
            try:
                self.cache.put(key, _entry_from_reply(reply))
            except OSError:
                pass  # a full or read-only cache folder must not lose a reply that was already paid for
        return reply


def _cacheable(reply: ModelReply) -> bool:
    if reply.finish_reason == "length" or any(c.parse_error for c in reply.tool_calls):
        return False
    return bool(reply.text) or bool(reply.tool_calls)


def _entry_from_reply(reply: ModelReply) -> dict:
    entry = {"text": reply.text, "model": reply.model, "finish_reason": reply.finish_reason,
             "tool_calls": [{"id": c.id, "name": c.name, "arguments": c.arguments} for c in reply.tool_calls]}
    if reply.raw is not None:
        entry["raw"] = reply.raw
    return entry


def _reply_from_entry(entry) -> ModelReply | None:
    """A stored entry -> a reply with zero usage, or None when the entry is not shaped like one."""
    try:
        text, calls = entry["text"], entry["tool_calls"]
        if not (text is None or isinstance(text, str)) or not isinstance(calls, list):
            return None
        tool_calls = []
        for c in calls:
            if not (isinstance(c["id"], str) and isinstance(c["name"], str) and isinstance(c["arguments"], dict)):
                return None
            tool_calls.append(ToolCall(id=c["id"], name=c["name"], arguments=c["arguments"]))
        raw = entry.get("raw")
        if raw is not None and not isinstance(raw, list):
            return None
        return ModelReply(text=text, tool_calls=tool_calls, usage={"input_tokens": 0, "output_tokens": 0},
                          model=entry.get("model"), finish_reason=entry.get("finish_reason"), cached=True, raw=raw)
    except (KeyError, TypeError, AttributeError):
        return None


DEFAULT_TIMEOUT = 60.0
# Verda Nemotron 3.5 Super VL: cold-start requests timed out at 60 s, a warm tool call took 69.2 s (probe,
# shared_context.md Section 7), so Verda clients wait at least this long whatever VENUS_MODEL_TIMEOUT says.
VERDA_MIN_TIMEOUT = 120.0


def _timeout_from(environ) -> float:
    """`VENUS_MODEL_TIMEOUT` (seconds, > 0) or the default. A bad value falls back to the default."""
    try:
        value = float(environ.get("VENUS_MODEL_TIMEOUT") or DEFAULT_TIMEOUT)
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT
    return value if value > 0 else DEFAULT_TIMEOUT


def _short(text, limit=300) -> str:
    text = str(text)
    return text if len(text) <= limit else text[:limit] + "..."
