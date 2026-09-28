"""Execution sandbox for LLM-generated code (basic version: no security yet)."""
import io
import traceback
from contextlib import redirect_stdout
from typing import Any


class Sandbox:
    """Run code with a persistent namespace and a built-in final_answer()."""

    def __init__(self) -> None:
        self.namespace: dict[str, Any] = {}
        self.is_done: bool = False
        self.final_answer_value: Any = None
        self.namespace["final_answer"] = self._final_answer

    def _final_answer(self, answer: Any) -> None:
        """Called when the LLM code runs final_answer(...): store it and stop the loop."""
        self.final_answer_value = answer
        self.is_done = True

    def run(self, code: str) -> str:
        """Execute code and return everything it printed, plus the traceback if it failed."""
        buffer = io.StringIO()
        try:
            with redirect_stdout(buffer):
                exec(code, self.namespace)
        except Exception:
            buffer.write(traceback.format_exc())
        return buffer.getvalue()