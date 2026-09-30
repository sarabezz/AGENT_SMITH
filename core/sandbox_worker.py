"""Entry point of the sandbox worker process: set OS-level limits, then run code on demand."""
import resource
import socket
from multiprocessing.connection import Connection
from typing import Any

from core.models_public import SandboxConfig
from core.sandbox_runtime import SandboxRuntime


def _block_network() -> None:
    """Unplug the network of this process: every way to open a connection raises an error."""
    def blocked(*args: Any, **kwargs: Any) -> Any:
        raise PermissionError("Network access is not allowed in the sandbox")

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


def worker_main(conn: Connection, config_data: dict[str, Any]) -> None:
    """Main loop of the worker: receive code, run it, send back the result."""
    config = SandboxConfig(**config_data)
    runtime = SandboxRuntime(config)
    _block_network()                         # protection 5: no network
    _limit_memory(config.max_memory_mb)      # protection 6: memory limit (set AFTER the imports)
    while True:
        try:
            code = conn.recv()
        except EOFError:                     # the agent closed the pipe: stop
            return
        output = runtime.run(code)
        conn.send({
            "output": output,
            "is_done": runtime.is_done,
            "final_answer": None if runtime.final_answer_value is None
            else str(runtime.final_answer_value),
        })