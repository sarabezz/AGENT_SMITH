"""Entry point of the sandbox worker process: set OS-level limits, then run code on demand."""
import resource
import socket
from multiprocessing.connection import Connection
from typing import Any

from core.models_public import SandboxConfig
from core.sandbox_runtime import SandboxRuntime
from core.tool_bridge import ToolCaller


def _block_network() -> None:
    """Unplug the network of this process: every way to open a connection raises an error."""
    def blocked(*args: Any, **kwargs: Any) -> Any:
        raise PermissionError("Network access is blocked by sandbox security policy")

    class BlockedSocket(socket.socket):
        """Still a class (other modules inherit from it), but creating one always fails."""
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            blocked()

    socket.socket = BlockedSocket            # type: ignore[misc]
    socket.create_connection = blocked       # type: ignore[assignment]
    socket.getaddrinfo = blocked             # type: ignore[assignment]


def _limit_memory(max_mb: int) -> None:
    """Ask the operating system to refuse more than max_mb of memory to this process."""
    limit = max_mb * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))


def _make_tool_caller(conn: Connection) -> ToolCaller:
    """The only way out of the sandbox: ask the agent (boss) to call an MCP tool for us."""
    def call_tool(name: str, arguments: dict[str, Any]) -> str:
        conn.send({"type": "tool_call", "name": name, "args": arguments})
        reply = conn.recv()                  # wait here until the boss sends the answer
        return reply["text"]
    return call_tool


def worker_main(conn: Connection, config_data: dict[str, Any],
                tool_specs: list[dict[str, Any]]) -> None:
    """Main loop of the worker: receive code, run it, send back the result."""
    config = SandboxConfig(**config_data)
    runtime = SandboxRuntime(config)
    runtime.add_tools(tool_specs, _make_tool_caller(conn))   # bridge functions for the MCP tools
    _block_network()                         # protection 5: no network
    _limit_memory(config.max_memory_mb)      # protection 6: memory limit (set AFTER the imports)
    while True:
        try:
            code = conn.recv()
        except EOFError:                     # the agent closed the pipe: stop
            return
        output = runtime.run(code)
        conn.send({
            "type": "result",
            "output": output,
            "ok": runtime.last_run_ok,
            "is_done": runtime.is_done,
            "final_answer": None if runtime.final_answer_value is None
            else str(runtime.final_answer_value),
        })