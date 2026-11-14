"""Use Venus from Python: one run request and one training request on the toy plugin.

    python examples/use_venus.py          # offline: a scripted FakeModel answers (no keys, no network)
    python examples/use_venus.py --live   # real models + web tools from .env (VERDA_*, CONTEXT_DEV_API_KEY)
"""
import json
import sys
from pathlib import Path

from venus import FakeModel, Venus, fake_text
from venus.serve import default_model_factory

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"


def offline_model(base_model):
    """Answers like a model would: negative if the text has 'not', else positive."""
    def reply(messages, tools, tool_choice):
        text = json.loads(messages[1]["content"].split("\n", 1)[1]).get("text", "")
        label = "negative" if "not" in text.lower().split() else "positive"
        return fake_text(json.dumps({"output": {"label": label}, "sources": []}))
    return FakeModel(reply)


def main(live: bool) -> None:
    options = dict(plugins_dir=FIXTURES, strategies_dir=FIXTURES / "strategies", runs_dir=None)
    if live:  # the toy strategy names "fake-model"; use the nemotron preset on Verda instead
        real = default_model_factory()
        venus = Venus(**options, model_factory=lambda base_model: real({"model": "nemotron"}))
    else:
        venus = Venus(**options, model_factory=offline_model, web_tools=[], env=False)

    run = {"venus_version": "1", "plugin": "toy-sentiment", "mode": "run", "strategy": "toy-validated",
           "input": {"text": "This is not good"}}
    print(json.dumps(venus.handle(run), indent=2))

    training = json.loads((ROOT / "examples" / "request_training.json").read_text())
    print(json.dumps(venus.handle(training), indent=2))


if __name__ == "__main__":
    main("--live" in sys.argv[1:])
