"""The sandbox as seen by the agent: LLM code runs in a separate worker process."""
import multiprocessing
from typing import Any

from core.models_public import SandboxConfig
from core.sandbox_worker import worker_main

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


class Sandbox:
    """Runs LLM code in a worker process with a time limit, a memory limit and no network."""

    def __init__(self, config: SandboxConfig | None = None) -> None:
        self.config = config if config is not None else SandboxConfig()   # secure by default
        self.is_done: bool = False
        self.final_answer_value: Any = None
        self.last_run_ok: bool = True     # did the last run() finish without errors?
        self._start_worker()

    def _start_worker(self) -> None:
        """Start a new worker process with an empty namespace."""
        self._conn, worker_conn = _CONTEXT.Pipe()
        self._process = _CONTEXT.Process(
            target=worker_main,
            args=(worker_conn, self.config.model_dump()),
            daemon=True,                  # the worker dies if the agent dies
        )
        self._process.start()
        worker_conn.close()               # the agent only uses its own end of the pipe

    def run(self, code: str) -> str:
        """Send code to the worker and wait for the result, at most max_execution_time_seconds."""
        timeout = self.config.max_execution_time_seconds
        self.last_run_ok = False
        try:
            self._conn.send(code)
            if not self._conn.poll(timeout):          # no answer in time: kill and restart
                self.close()
                self._start_worker()
                return TIMEOUT_MESSAGE.format(seconds=timeout)
            reply = self._conn.recv()
        except (EOFError, BrokenPipeError, ConnectionResetError):   # the worker died
            self._process.join(timeout=1)             # let it finish dying to read its exit code
            self.close()
            exit_code = self._process.exitcode
            self._start_worker()
            return CRASH_MESSAGE.format(code=exit_code)

        self.last_run_ok = reply["ok"]
        if reply["is_done"]:
            self.is_done = True
            self.final_answer_value = reply["final_answer"]
        return reply["output"]

    def close(self) -> None:
        """Stop the worker process (always call this when the task is over)."""
        if self._process.is_alive():
            self._process.kill()
        self._process.join()
        self._conn.close()