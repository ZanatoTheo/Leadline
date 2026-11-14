"""A scripted stand-in for ModelClient, for tests. Same `.chat(...)` signature; records every call."""
import itertools

from .errors import ModelError
from .models import ModelReply, ToolCall, tool_choice_param

_ids = itertools.count(1)


def fake_text(text: str, input_tokens: int = 0, output_tokens: int = 0) -> ModelReply:
    return ModelReply(text=text, usage={"input_tokens": input_tokens, "output_tokens": output_tokens},
                      model="fake-model", finish_reason="stop")


def fake_tool_call(name: str, args: dict, id: str | None = None) -> ModelReply:
    call = ToolCall(id=id or f"call_fake_{next(_ids)}", name=name, arguments=args)
    return ModelReply(text=None, tool_calls=[call], model="fake-model", finish_reason="tool_calls")


class FakeModel:
    """`script` is a list of ModelReply (served in order) or a function (messages, tools, tool_choice) -> ModelReply.
    `tool_choices` (optional) plays a provider that accepts only those choices: any other string choice is refused
    with `model_bad_request`, as the real API would."""

    def __init__(self, script, budget=None, tool_choices=None):
        self.script = script if callable(script) else list(script)
        self.budget = budget
        self.tool_choices = tuple(tool_choices) if tool_choices is not None else None
        self.calls = []

    def chat(self, messages, tools=None, tool_choice=None, max_tokens=1024, temperature=None, seed=None) -> ModelReply:
        if self.budget is not None:
            self.budget.check()
        tool_choice_param(tool_choice)  # same validation as the real client
        if self.tool_choices is not None and isinstance(tool_choice, str) and tool_choice not in self.tool_choices:
            raise ModelError("model_bad_request", f"tool_choice {tool_choice!r} not supported by this provider")
        self.calls.append({"messages": [dict(m) for m in messages], "tools": tools, "tool_choice": tool_choice,
                           "max_tokens": max_tokens, "temperature": temperature, "seed": seed})
        if callable(self.script):
            reply = self.script(messages, tools, tool_choice)
        elif self.script:
            reply = self.script.pop(0)
        else:
            raise ModelError("model_bad_reply", "FakeModel script ran out of replies")
        if self.budget is not None:
            self.budget.charge(reply.usage["input_tokens"], reply.usage["output_tokens"])
        return reply
