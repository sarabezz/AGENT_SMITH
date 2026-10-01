"""Interactive sandbox: `uv run sandbox [config.json]` — type Python code, it runs in the secure sandbox.

With MCP tools:
  uv run sandbox --mcp-stdio "python mcp_tools_mbpp.py" [config.json]   (starts the server)
  uv run sandbox --mcp-server http://127.0.0.1:8000/mcp [config.json]   (server already running)
"""
import argparse
import ast
import codeop
import os
import shlex
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from core.models_public import SandboxConfig
from core.sandbox import Sandbox
from core.tool_bridge import python_name
from mcp_client import McpClientManager

EXIT_COMMANDS = ("exit", "exit()", "quit", "quit()")
PROMPT = ">>> "
CONTINUATION = "... "


def parse_args() -> argparse.Namespace:
    """Read the command-line options."""
    parser = argparse.ArgumentParser(prog="sandbox",
                                     description="Interactive secure sandbox for LLM-generated code.")
    parser.add_argument("config", nargs="?", type=Path,
                        help="Sandbox configuration JSON (default: the secure empty configuration)")
    mcp = parser.add_mutually_exclusive_group()
    mcp.add_argument("--mcp-stdio", metavar="COMMAND",
                     help='Start an MCP server and use its tools, e.g. "python mcp_tools_mbpp.py"')
    mcp.add_argument("--mcp-server", metavar="URL",
                     help="Use the tools of a running MCP server, e.g. http://127.0.0.1:8000/mcp")
    return parser.parse_args()


def load_config(path: Path | None) -> SandboxConfig:
    """Load the configuration file, or return the secure default configuration."""
    if path is None:
        return SandboxConfig()
    return SandboxConfig.model_validate_json(path.read_text())


def connect_mcp(args: argparse.Namespace) -> McpClientManager | None:
    """Connect to the MCP server given on the command line (None if no server was given)."""
    if args.mcp_stdio:
        # the server gets our environment, so MBPP_TASK_FILE=... uv run sandbox ... works
        return McpClientManager(stdio_cmd=shlex.split(args.mcp_stdio), env=dict(os.environ))
    if args.mcp_server:
        return McpClientManager(server_url=args.mcp_server)
    return None


def tool_signature(tool: Any) -> str:
    """'run_tests(code)' from the tools/list information."""
    params = list((tool.inputSchema or {}).get("properties", {}))
    return f"{python_name(tool.name)}({', '.join(params)})"


def print_banner(config: SandboxConfig, mcp_client: McpClientManager | None) -> None:
    """Show which rules and which tools are active."""
    allowed = ", ".join(config.authorized_imports) or "none"
    directories = ", ".join(config.allowed_directories) or "none"
    tools = ", ".join(tool_signature(t) for t in mcp_client.tools) if mcp_client else "none"
    print("Secure sandbox. Type Python code; an empty line ends a multi-line block.")
    print(f"  imports allowed : {allowed}")
    print(f"  directories     : {directories}")
    print(f"  limits          : {config.max_execution_time_seconds} s, {config.max_memory_mb} MB, no network")
    print(f"  MCP tools       : {tools}")
    print("  final_answer    : final_answer(value) submits a value")
    print("  exit            : type exit, or press Ctrl+D\n")


def read_block() -> str | None:
    """Read one complete piece of code, like the Python prompt. Returns None when the user quits."""
    lines: list[str] = []
    while True:
        try:
            line = input(PROMPT if not lines else CONTINUATION)
        except EOFError:                                  # Ctrl+D
            print()
            return None
        lines.append(line)
        source = "\n".join(lines)
        if len(lines) == 1 and not line.strip():          # empty line: nothing to run
            return ""
        try:
            complete = codeop.compile_command(source, "<sandbox>", "exec")
        except SyntaxError:
            return source                                 # the sandbox will explain the error
        if complete is not None and (len(lines) == 1 or line == ""):
            return source


def show_expression_value(code: str) -> str:
    """Like the Python prompt: if the input is a single expression, also print its value."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code                                       # the sandbox will explain the error
    if len(tree.body) == 1 and isinstance(tree.body[0], ast.Expr):
        return (f"_repl_value = ({code})\n"
                "if _repl_value is not None:\n"
                "    print(repr(_repl_value))")
    return code


def main() -> None:
    args = parse_args()
    try:
        config = load_config(args.config)
    except (OSError, ValidationError) as exc:
        print(f"Error: could not load the sandbox config: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        mcp_client = connect_mcp(args)
    except Exception as exc:
        print(f"Error: could not connect to the MCP server: {exc}", file=sys.stderr)
        sys.exit(1)

    print_banner(config, mcp_client)
    sandbox = Sandbox(config, mcp_client=mcp_client)
    answer_shown = False
    try:
        while True:
            code = read_block()
            if code is None or code.strip() in EXIT_COMMANDS:
                break
            if not code.strip():
                continue
            output = sandbox.run(show_expression_value(code))
            print(output if output.endswith("\n") or not output else output + "\n", end="")
            if sandbox.is_done and not answer_shown:
                print(f"[final_answer received]\n{sandbox.final_answer_value}")
                answer_shown = True
    except KeyboardInterrupt:                             # Ctrl+C: shut down cleanly, not silently
        print("\nInterrupted (Ctrl+C).")
    finally:
        sandbox.close()
        if mcp_client is not None:
            mcp_client.close()                            # also stops a server started with --mcp-stdio
        print("Sandbox closed.")


if __name__ == "__main__":
    main()