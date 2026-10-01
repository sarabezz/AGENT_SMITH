"""The sandbox as seen by the agent: LLM code runs in a separate worker process."""
import multiprocessing
import time
from typing import Any

from core.models_public import SandboxConfig
from core.sandbox_worker import worker_main
from core.tool_bridge import tool_specs_from

_CONTEXT = multiprocessing.get_context("spawn")   # a fresh, clean Python for each worker

TIMEOUT_MESSAGE = (
    "TimeoutError: the execution exceeded {seconds} s and was stopped. "
    "The sandbox was restarted: all previous variables and functions are lost, "
    "define again what you need."
)
CRASH_MESSAGE = (
    "SandboxCrash: the sandbox process stopped unexpectedly (exit code {code}), "
    "for example because the code raised SystemExit. The sandbox was restarted: "
    "all previous variables and functions are lost, define again what you need."
)
NO_SERVER_MESSAGE = "Tool error: no MCP server is connected"


class Sandbox:
    """Runs LLM code in a worker process with a time limit, a memory limit and no network.

    If an MCP client is given, its tools are available in the code as normal functions.
    The Sandbox does NOT own the client: whoever created it must close it.
    """

    def __init__(self, config: SandboxConfig | None = None, mcp_client: Any = None) -> None:
        self.config = config if config is not None else SandboxConfig()   # secure by default
        self.mcp_client = mcp_client
        self.tool_specs = tool_specs_from(mcp_client.tools) if mcp_client else []
        self.is_done: bool = False
        self.final_answer_value: Any = None
        self.last_run_ok: bool = True     # did the last run() finish without errors?
        self._start_worker()

    def _start_worker(self) -> None:
        """Start a new worker process with an empty namespace (plus final_answer and the tools)."""
        self._conn, worker_conn = _CONTEXT.Pipe()
        self._process = _CONTEXT.Process(
            target=worker_main,
            args=(worker_conn, self.config.model_dump(), self.tool_specs),
            daemon=True,                  # the worker dies if the agent dies
        )
        self._process.start()
        worker_conn.close()               # the agent only uses its own end of the pipe

    def _call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """Run a tool for the worker through the MCP client. Never raises: errors become text."""
        if self.mcp_client is None:
            return NO_SERVER_MESSAGE
        try:
            return self.mcp_client.call_tool(name, arguments)
        except Exception as exc:
            return f"Tool error: {type(exc).__name__}: {exc}"

    def run(self, code: str) -> str:
        """Send code to the worker and wait for the result.

        The time limit only counts the time spent running code in the sandbox:
        while an MCP tool is running, the clock is paused.
        """
        timeout = self.config.max_execution_time_seconds
        self.last_run_ok = False
        try:
            self._conn.send(code)
            deadline = time.monotonic() + timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not self._conn.poll(remaining):   # no answer in time
                    self.close()
                    self._start_worker()
                    return TIMEOUT_MESSAGE.format(seconds=timeout)
                message = self._conn.recv()
                if message["type"] != "tool_call":                     # the code finished
                    break
                tool_start = time.monotonic()                          # pause the clock...
                text = self._call_tool(message["name"], message["args"])
                deadline += time.monotonic() - tool_start              # ...and resume it
                self._conn.send({"type": "tool_result", "text": text})
        except (EOFError, BrokenPipeError, ConnectionResetError):   # the worker died
            self._process.join(timeout=1)             # let it finish dying to read its exit code
            self.close()
            exit_code = self._process.exitcode
            self._start_worker()
            return CRASH_MESSAGE.format(code=exit_code)

        self.last_run_ok = message["ok"]
        if message["is_done"]:
            self.is_done = True
            self.final_answer_value = message["final_answer"]
        return message["output"]

    def close(self) -> None:
        """Stop the worker process (always call this when the task is over)."""
        if self._process.is_alive():
            self._process.kill()
        self._process.join()
        self._conn.close()