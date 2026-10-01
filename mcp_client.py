"""MCP client used by the sandbox: connects to ONE MCP server (stdio or streamable HTTP)."""
import asyncio
import os
import threading
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import TextContent, Tool

CALL_TIMEOUT_SECONDS = 300.0


class McpClientManager:
    """Synchronous wrapper around the (asynchronous) MCP client.

    The MCP library is async, the rest of our code is not: a background thread runs an
    asyncio event loop that keeps the connection open, and every public method sends its
    work to that loop and waits for the answer.
    """

    def __init__(self, stdio_cmd: list[str] | None = None, server_url: str | None = None,
                 env: dict[str, str] | None = None) -> None:
        if (stdio_cmd is None) == (server_url is None):
            raise ValueError("give exactly one of stdio_cmd or server_url")
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()
        self._stack = AsyncExitStack()
        self._session: ClientSession | None = None
        self.tools: list[Tool] = []
        try:
            self._run(self._connect(stdio_cmd, server_url, env))
            self.tools = self._run(self._list_tools())
        except Exception:
            self.close()
            raise

    # ---------- helpers ----------

    def _run(self, coroutine: Any, timeout: float = CALL_TIMEOUT_SECONDS) -> Any:
        """Run a coroutine on the background loop and wait for its result."""
        return asyncio.run_coroutine_threadsafe(coroutine, self._loop).result(timeout)

    async def _connect(self, stdio_cmd: list[str] | None, server_url: str | None,
                       env: dict[str, str] | None) -> None:
        """Open the transport (stdio or HTTP) and the MCP session, then say hello."""
        if stdio_cmd is not None:
            params = StdioServerParameters(command=stdio_cmd[0], args=stdio_cmd[1:],
                                           env={**os.environ, **(env or {})})
            read, write = await self._stack.enter_async_context(stdio_client(params))
        else:
            read, write, _ = await self._stack.enter_async_context(streamablehttp_client(server_url))
        self._session = await self._stack.enter_async_context(ClientSession(read, write))
        await self._session.initialize()

    async def _list_tools(self) -> list[Tool]:
        """Ask the server for its tools (tools/list)."""
        assert self._session is not None
        return (await self._session.list_tools()).tools

    async def _call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """Call one tool (tools/call) and return the text of its answer."""
        assert self._session is not None
        result = await self._session.call_tool(name, arguments)
        text = "\n".join(part.text for part in result.content if isinstance(part, TextContent))
        return f"Tool error: {text}" if result.isError else text

    # ---------- public API ----------

    def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """Call one tool of the server and return its answer as plain text."""
        return self._run(self._call_tool(name, arguments))

    def close(self) -> None:
        """Close the connection (and stop the server if we started it)."""
        if self._loop.is_running():
            try:
                self._run(self._stack.aclose(), timeout=10)
            except Exception:
                pass
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=5)