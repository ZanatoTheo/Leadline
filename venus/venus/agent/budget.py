"""Caps on model calls, tokens and wall time. `check()` before a call, `charge()` after it."""
import time

from .errors import BudgetExceeded


class Budget:
    def __init__(self, max_model_calls=None, max_input_tokens=None, max_output_tokens=None, max_seconds=None,
                 clock=time.monotonic):
        self.max_model_calls = max_model_calls
        self.max_input_tokens = max_input_tokens
        self.max_output_tokens = max_output_tokens
        self.max_seconds = max_seconds
        self._clock = clock
        self._start = clock()
        self.model_calls = 0
        self.input_tokens = 0
        self.output_tokens = 0

    def seconds(self) -> float:
        return self._clock() - self._start

    def check(self) -> None:
        for used, cap, what in ((self.model_calls, self.max_model_calls, "model calls"),
                                (self.input_tokens, self.max_input_tokens, "input tokens"),
                                (self.output_tokens, self.max_output_tokens, "output tokens"),
                                (self.seconds(), self.max_seconds, "seconds")):
            if cap is not None and used >= cap:
                raise BudgetExceeded(f"{what}: used {used:g} of {cap:g}")

    def charge(self, input_tokens: int = 0, output_tokens: int = 0) -> None:
        self.model_calls += 1
        self.input_tokens += input_tokens or 0
        self.output_tokens += output_tokens or 0

    def spent(self) -> dict:
        return {"model_calls": self.model_calls, "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens, "seconds": round(self.seconds(), 3)}
