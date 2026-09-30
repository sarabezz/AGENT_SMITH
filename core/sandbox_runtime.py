"""Code executor that runs INSIDE the sandbox worker process, with all in-process protections."""
import ast
import builtins
import fnmatch
import io
import os
import traceback
from collections.abc import Callable
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

from core.models_public import SandboxConfig

# Builtins the LLM code must never use (see the README for the reason of each one)
BLOCKED_BUILTINS = (
    "eval", "exec", "compile",          # run text as code: bypass every other check
    "input", "breakpoint", "help",      # interactive: would hang the agent forever
    "exit", "quit",                     # would close the whole agent
    "globals", "locals", "vars",        # access to the namespaces (and our builtins)
    "getattr", "setattr", "delattr",    # access attributes by name: classic way to escape checks
)


class SandboxSecurityError(Exception):
    """Raised when LLM code tries to do something the sandbox forbids."""


def _make_blocked(name: str) -> Callable[..., Any]:
    """Build a replacement for a forbidden builtin that always raises a clear error."""
    def blocked(*args: Any, **kwargs: Any) -> Any:
        raise PermissionError(f"The builtin '{name}' is not allowed in the sandbox")
    return blocked


class SandboxRuntime:
    """Run code with a persistent namespace, a built-in final_answer() and security checks."""

    def __init__(self, config: SandboxConfig | None = None) -> None:
        self.config = config if config is not None else SandboxConfig()   # secure by default
        self.is_done: bool = False
        self.final_answer_value: Any = None
        self.executed_code: list[str] = []
        self.namespace: dict[str, Any] = {
            "__builtins__": self._build_safe_builtins(),
            "final_answer": self._final_answer,
        }

    def _build_safe_builtins(self) -> dict[str, Any]:
        """A private COPY of Python's builtins with every protection plugged in."""
        safe_builtins = dict(vars(builtins))
        safe_builtins["__import__"] = self._safe_import           # protection 1
        for name in BLOCKED_BUILTINS:                             # protection 2
            safe_builtins[name] = _make_blocked(name)
        safe_builtins["open"] = self._safe_open                   # protection 4
        return safe_builtins

    # ---------- Protection 1: imports ----------

    def _is_import_allowed(self, module_name: str) -> bool:
        """True if the module matches one of the authorized patterns (e.g. 'math', 'collections.*')."""
        return any(fnmatch.fnmatch(module_name, pattern)
                   for pattern in self.config.authorized_imports)

    def _safe_import(self, name: str, globals: Any = None, locals: Any = None,
                     fromlist: Any = (), level: int = 0) -> Any:
        """Replacement for __import__: only modules in the allowlist can be imported."""
        if level != 0:
            raise ImportError("Relative imports are not allowed in the sandbox")
        if not self._is_import_allowed(name):
            allowed = ", ".join(p for p in self.config.authorized_imports if "*" not in p)
            raise ImportError(f"Import of '{name}' is not allowed in the sandbox. "
                              f"Allowed modules: {allowed or 'none'}")
        return builtins.__import__(name, globals, locals, fromlist, level)

    # ---------- Protection 3: static check of the code before running it ----------

    def _check_code(self, code: str) -> None:
        """Reject code that touches private/dunder names (back doors like random._os or __class__)."""
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
                raise SandboxSecurityError(
                    f"line {node.lineno}: access to the attribute '{node.attr}' is not allowed "
                    "(attribute names starting with '_' are blocked in the sandbox)")
            if isinstance(node, ast.Name) and node.id.startswith("__"):
                raise SandboxSecurityError(
                    f"line {node.lineno}: the name '{node.id}' is not allowed in the sandbox")

    # ---------- Protection 4: filesystem ----------

    def _is_path_allowed(self, real_path: Path) -> bool:
        """True if the (already resolved) path is inside one of the allowed directories."""
        return any(real_path.is_relative_to(Path(directory).resolve())
                   for directory in self.config.allowed_directories)

    def _safe_open(self, file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        """Replacement for open(): only files inside the allowed directories."""
        if not isinstance(file, (str, os.PathLike)):
            raise PermissionError("open() only accepts a file path in the sandbox")
        real_path = Path(file).resolve()          # undo '..' and symlinks BEFORE checking
        if not self._is_path_allowed(real_path):
            allowed = ", ".join(self.config.allowed_directories) or "none"
            raise PermissionError(f"Access to '{file}' is not allowed in the sandbox. "
                                  f"Allowed directories: {allowed}")
        return builtins.open(real_path, mode, *args, **kwargs)

    # ---------- final_answer ----------

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
                continue
            for node in tree.body:
                segment = ast.get_source_segment(code, node) or ""
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    if segment not in imports:
                        imports.append(segment)
                elif isinstance(node, ast.FunctionDef) and node.name == name:
                    definition = segment
        if not definition:
            raise ValueError(f"final_answer: could not find the source code of '{name}'")
        return "\n".join(imports + [definition])

    # ---------- Execution ----------

    def run(self, code: str) -> str:
        """Check the code, execute it, and return everything it printed (plus any error)."""
        buffer = io.StringIO()
        try:
            self._check_code(code)                 # protection 3: BEFORE running anything
            self.executed_code.append(code)        # only code that passed the check is recorded
            with redirect_stdout(buffer):
                exec(code, self.namespace)
        except SandboxSecurityError as exc:
            buffer.write(f"SandboxSecurityError: {exc}\n")
        except MemoryError:
            buffer.write(f"MemoryError: the code exceeded the sandbox memory limit "
                         f"of {self.config.max_memory_mb} MB\n")
        except Exception:
            buffer.write(traceback.format_exc())
        return buffer.getvalue()