"""Execution sandbox for LLM-generated code (basic version: no security yet)."""
import ast
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
        self.executed_code: list[str] = []      # every code block run so far
        self.namespace["final_answer"] = self._final_answer

    def _final_answer(self, answer: Any) -> None:
        """Called when the LLM code runs final_answer(...).

        Accepts the solution as a string, or directly as a function:
        in that case its source code is recovered from the code already executed.
        """
        if callable(answer):
            answer = self._source_of(answer.__name__)
        self.final_answer_value = answer
        self.is_done = True

    def _source_of(self, name: str) -> str:
        """Return the imports plus the latest definition of function `name` in the executed code."""
        imports: list[str] = []
        definition = ""
        for code in self.executed_code:
            try:
                tree = ast.parse(code)
            except SyntaxError:
                continue                        # skip blocks that were not valid Python
            for node in tree.body:
                segment = ast.get_source_segment(code, node) or ""
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    if segment not in imports:
                        imports.append(segment)
                elif isinstance(node, ast.FunctionDef) and node.name == name:
                    definition = segment        # a later definition replaces an earlier one
        if not definition:
            raise ValueError(f"final_answer: could not find the source code of '{name}'")
        return "\n".join(imports + [definition])

    def run(self, code: str) -> str:
        """Execute code and return everything it printed, plus the traceback if it failed."""
        self.executed_code.append(code)         # saved BEFORE running: final_answer may need it
        buffer = io.StringIO()
        try:
            with redirect_stdout(buffer):
                exec(code, self.namespace)
        except Exception:
            buffer.write(traceback.format_exc())
        return buffer.getvalue()