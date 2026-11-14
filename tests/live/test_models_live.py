"""Model providers, for real. Per model: a plain chat, a tool call under "auto" with an instruction, then a final answer
after the tool result (the reply's own blocks replayed unchanged; "none" where supported, else no tools). 3 calls each.
Anthropic runs by default (each distinct model of the claude-research / claude-fast presets once); Meta, Verda, NVIDIA
and Gemini need their own switch."""
import json
import os
import time

import pytest
from conftest import need

from venus.config import resolve_model
from venus.models import function_tool
from venus.serve import default_model_factory

SEARCH = function_tool("web_search", "Search the web and return result titles and URLs.", {
    "type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]})


def _anthropic_models():
    env = dict(os.environ)
    ids = []
    for preset in ("claude-research", "claude-fast"):
        model = resolve_model({"model": preset}, env).model
        if model not in ids:
            ids.append(model)
    return [pytest.param({"model": m, "provider": "anthropic"}, "ANTHROPIC_API_KEY", None, id=f"anthropic-{m}")
            for m in ids]


CASES = _anthropic_models() + [
    pytest.param({"model": "meta"}, "META_API_KEY|MODEL_API_KEY", "VENUS_LIVE_META", id="meta"),
    pytest.param({"model": os.environ.get("VENUS_TRAIN_MODEL") or "kimi-k3-1-pro", "provider": "verda"},
                 "VERDA_API_KEY", "VENUS_LIVE_VERDA", id="verda"),
    pytest.param({"model": "nemotron", "provider": "nvidia"}, "NVIDIA_API_KEY", "VENUS_LIVE_NVIDIA", id="nvidia"),
    pytest.param({"model": "gemini"}, "GEMINI_API_KEY", "VENUS_LIVE_GEMINI", id="gemini"),
]


def _model(base_model):
    env = {k: v for k, v in os.environ.items() if k != "VENUS_MODEL_CACHE"}  # real calls, not cache hits
    return default_model_factory(max_model_calls=5, environ=env)(base_model)


@pytest.mark.parametrize("base_model,key,switch", CASES)
def test_chat_tool_call_and_round_trip(base_model, key, switch):
    need(key, switch=switch)
    model = _model(base_model)
    start = time.monotonic()
    plain = model.chat([{"role": "user", "content": "Reply with the single word: ok"}], max_tokens=200)
    assert plain.text and "ok" in plain.text.lower()

    msgs = [{"role": "system", "content": "You research companies. Use the web_search tool before answering."},
            {"role": "user", "content": "Who founded the Finnish company Supercell? Call web_search first."}]
    first = model.chat(msgs, tools=[SEARCH], tool_choice="auto", max_tokens=400)
    searched = bool(first.tool_calls)
    print(f"\nMODEL {base_model} -> {first.model}: searched on first turn: {'yes' if searched else 'no'}")
    assert searched, f"no tool call under auto; text: {(first.text or '')[:200]}"
    call = first.tool_calls[0]
    assert call.name == "web_search" and isinstance((call.arguments or {}).get("query"), str)

    msgs.append({"role": "assistant", "content": first.text, "_raw": first.raw, "tool_calls": [
        {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": json.dumps(c.arguments or {})}}
        for c in first.tool_calls]})
    for c in first.tool_calls:
        msgs.append({"role": "tool", "tool_call_id": c.id, "content": json.dumps({"results": [
            {"title": "Supercell - Wikipedia", "url": "https://en.wikipedia.org/wiki/Supercell_(video_game_company)",
             "description": "Founded in 2010 by Ilkka Paananen, Mikko Kodisoja and others."}]})})
    msgs.append({"role": "user", "content": "Answer now in one sentence, no more tool calls."})
    if "none" in model.tool_choices:
        final = model.chat(msgs, tools=[SEARCH], tool_choice="none", max_tokens=400)
    else:
        final = model.chat(msgs, max_tokens=400)
    assert final.text and "paananen" in final.text.lower(), final.text
    tokens = sum(r.usage["input_tokens"] + r.usage["output_tokens"] for r in (plain, first, final))
    print(f"MODEL {first.model}: 3 calls, {time.monotonic() - start:.1f}s, {tokens} tokens, "
          f"tool_choices={model.tool_choices}")
