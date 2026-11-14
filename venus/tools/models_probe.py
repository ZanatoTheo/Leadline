"""Manual check of the real model endpoints (not a test; needs keys in .env).

For each preset on each configured provider: a plain chat, a tool call ("required" where the provider allows it, else "auto") with a dummy
web_search tool, and a tool-result round trip. Prints OK/FAIL lines with the model id and latency.

    .venv/bin/python tools/models_probe.py            # all presets, every provider that has a key
    .venv/bin/python tools/models_probe.py nemotron   # one preset
"""
import json
import os
import sys
import time

from venus.config import PRESETS, PROVIDERS, resolve_model
from venus.envfile import find_env_file, load_env
from venus.errors import VenusError
from venus.models import ModelClient, function_tool

SEARCH = function_tool("web_search", "Search the web and return result titles and URLs.", {
    "type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]})


def timed(label, spec, fn):
    start = time.monotonic()
    try:
        detail = fn()
        print(f"OK   {label:<14} {spec.provider}/{spec.model}  {time.monotonic() - start:.1f}s  {detail}")
        return True
    except (VenusError, AssertionError) as e:
        print(f"FAIL {label:<14} {spec.provider}/{spec.model}  {time.monotonic() - start:.1f}s  {e}")
        return False


def probe(spec):
    if spec.client == "anthropic":
        from venus.anthropic_client import AnthropicClient
        client = AnthropicClient(spec, max_attempts=2)
    else:
        client = ModelClient(spec, max_attempts=2)
    choice = "required" if "required" in spec.tool_choices else "auto"  # some providers refuse forced tool use
    ask = [{"role": "user", "content": "Find one recent news story about Finnish startups. Use the tool."}]

    def plain():
        reply = client.chat([{"role": "user", "content": "Reply with the single word: ready"}], max_tokens=50)
        assert reply.text, "empty text"
        return repr(reply.text.strip()[:40])

    def forced():
        reply = client.chat(ask, tools=[SEARCH], tool_choice=choice, max_tokens=200)
        assert reply.tool_calls, f"no tool call (finish={reply.finish_reason}, text={reply.text!r:.60})"
        call = reply.tool_calls[0]
        assert call.parse_error is None, call.parse_error
        probe.last = (reply, call)
        return f"{call.name}({call.arguments})"

    def round_trip():
        reply, call = probe.last
        messages = ask + [
            {"role": "assistant", "content": reply.text, "_raw": reply.raw,
             "tool_calls": [{"id": call.id, "type": "function",
                             "function": {"name": call.name, "arguments": json.dumps(call.arguments)}}]},
            {"role": "tool", "tool_call_id": call.id,
             "content": '[{"title": "Example startup raises seed round", "url": "https://example.com/news/1"}]'},
        ]
        final = client.chat(messages, tools=[SEARCH], max_tokens=200)
        assert final.text or final.tool_calls, "empty reply after tool result"
        return repr((final.text or "<tool call>").strip()[:60])

    results = [timed("plain chat", spec, plain), timed(f"tool ({choice})", spec, forced)]
    if results[-1]:
        results.append(timed("tool round trip", spec, round_trip))
    return all(results)


def main(argv):
    env_file = find_env_file()
    load_env()
    print(f"env file: {env_file or 'none found'}")
    presets = argv or list(PRESETS)
    ok = True
    for provider, info in PROVIDERS.items():
        if not (os.environ.get(info["key_env"]) or os.environ.get(info.get("key_env_alt") or "")):
            print(f"skip {provider}: {info['key_env']} not set")
            continue
        for preset in presets:
            own = PRESETS[preset][2] if preset in PRESETS and len(PRESETS[preset]) > 2 else None
            if own != provider and not (own is None and provider in ("verda", "nvidia")):
                continue  # a preset only runs on its own provider (provider-less presets: verda and nvidia)
            try:
                spec = resolve_model({"model": preset, "provider": provider})
            except VenusError as e:
                print(f"skip {provider}/{preset}: {e}")
                continue
            ok = probe(spec) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
