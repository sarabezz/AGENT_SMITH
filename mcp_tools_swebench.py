"""MCP server with the SWE-bench tools (files of a code repository).

Start it (stdio):  python mcp_tools_swebench.py
Start it (HTTP):   python mcp_tools_swebench.py --http --port 8001  ->  http://127.0.0.1:8001/mcp
The repository is the folder given in the SWEBENCH_REPO_DIR environment variable
(default: the current folder). Every path is relative to it and can never leave it.
Tools that need the Docker container (run_tests, get_patch, run_command) come in phase 8.
"""
import argparse
import os
import re
from pathlib import Path

from mcp.server.fastmcp import FastMCP

REPO_DIR_ENV = "SWEBENCH_REPO_DIR"
MAX_LINES = 300                 # read_file: at most this many lines per call
MAX_ENTRIES = 200               # list_files: at most this many entries
MAX_MATCHES = 50                # search_code: at most this many results
SKIPPED_DIRS = {".git", "__pycache__", ".venv", "node_modules"}

server = FastMCP("swebench-tools", log_level="WARNING")


def repo_root() -> Path:
    """The repository folder the tools work on."""
    return Path(os.environ.get(REPO_DIR_ENV, ".")).resolve()


def safe_path(path: str) -> Path:
    """Resolve `path` inside the repository; refuse anything outside it (e.g. '../../etc')."""
    root = repo_root()
    real_path = (root / path).resolve()            # undo '..' and symlinks BEFORE checking
    if not real_path.is_relative_to(root):
        raise ValueError(f"'{path}' is outside the repository")
    return real_path


@server.tool()
def read_file(path: str, start_line: int = 1, end_line: int = 0) -> str:
    """Read a file of the repository, with line numbers.

    `path` is relative to the repository root. Use start_line/end_line to read a part
    of a long file (end_line 0 = until the end). At most 300 lines are returned per call.
    """
    file = safe_path(path)
    if not file.is_file():
        raise ValueError(f"'{path}' is not a file")
    lines = file.read_text(errors="replace").splitlines()
    first = max(start_line, 1)
    last = len(lines) if end_line <= 0 else min(end_line, len(lines))
    last = min(last, first + MAX_LINES - 1)
    numbered = [f"{n:5d} | {lines[n - 1]}" for n in range(first, last + 1)]
    footer = f"[lines {first}-{last} of {len(lines)}]"
    return "\n".join(numbered + [footer])


@server.tool()
def list_files(path: str = ".") -> str:
    """List the files and folders inside a folder of the repository (folders end with '/')."""
    folder = safe_path(path)
    if not folder.is_dir():
        raise ValueError(f"'{path}' is not a folder")
    entries = sorted(e for e in folder.iterdir()
                     if e.name not in SKIPPED_DIRS and not e.name.startswith("."))
    names = [e.name + ("/" if e.is_dir() else "") for e in entries]
    if len(names) > MAX_ENTRIES:
        names = names[:MAX_ENTRIES] + [f"[... {len(entries) - MAX_ENTRIES} more]"]
    return "\n".join(names) if names else "(empty folder)"


@server.tool()
def search_code(pattern: str, path: str = ".") -> str:
    """Search a regular expression in the .py files of the repository.

    Returns 'file:line: text' for each match (at most 50).
    """
    try:
        regex = re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"invalid regular expression: {exc}") from None
    root = repo_root()
    start = safe_path(path)
    files = [start] if start.is_file() else sorted(start.rglob("*.py"))
    matches: list[str] = []
    for file in files:
        if any(part in SKIPPED_DIRS for part in file.relative_to(root).parts):
            continue
        for number, line in enumerate(file.read_text(errors="replace").splitlines(), 1):
            if regex.search(line):
                matches.append(f"{file.relative_to(root)}:{number}: {line.strip()}")
                if len(matches) >= MAX_MATCHES:
                    return "\n".join(matches + [f"[stopped after {MAX_MATCHES} matches]"])
    return "\n".join(matches) if matches else "No matches found"


@server.tool()
def edit_file(path: str, old_text: str, new_text: str) -> str:
    """Replace `old_text` by `new_text` in a file of the repository.

    `old_text` must appear EXACTLY ONCE in the file (copy it with its indentation);
    include more surrounding lines if it appears several times.
    """
    file = safe_path(path)
    if not file.is_file():
        raise ValueError(f"'{path}' is not a file")
    content = file.read_text()
    count = content.count(old_text)
    if count == 0:
        raise ValueError("old_text was not found in the file (check spaces and indentation)")
    if count > 1:
        raise ValueError(f"old_text appears {count} times; include more lines to make it unique")
    file.write_text(content.replace(old_text, new_text))
    return f"Edited {path}: 1 replacement"


def main() -> None:
    parser = argparse.ArgumentParser(description="MCP server with the SWE-bench tools.")
    parser.add_argument("--http", action="store_true", help="Serve over streamable HTTP instead of stdio")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    if args.http:
        server.settings.port = args.port
        server.run(transport="streamable-http")
    else:
        server.run()                          # stdio


if __name__ == "__main__":
    main()