"""Entry point expected by the evaluation (`import sandbox`): a thin wrapper around core.sandbox."""
from core.models_public import SandboxConfig
from core.sandbox import Sandbox


class ExecutionSandbox:
    """Evaluation-facing name for our Sandbox: execute(code) returns what happened as text."""

    def __init__(self, config: SandboxConfig | None = None) -> None:
        self._sandbox = Sandbox(config)

    def execute(self, code: str) -> str:
        """Run code in the secure worker and return its output (or the error)."""
        return self._sandbox.run(code)

    def close(self) -> None:
        """Stop the worker process."""
        self._sandbox.close()