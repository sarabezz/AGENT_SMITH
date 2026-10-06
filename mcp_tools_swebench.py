"""MCP server with the SWE-bench tools: explore, edit and test a code repository.

Two modes, chosen with environment variables:
- Docker mode (real SWE-bench): SWEBENCH_CONTAINER=<container name>. Every tool runs inside
  that container with `docker exec`; the repository is /testbed.
- Local mode (tests, exam test 7): SWEBENCH_REPO_DIR=<folder> (default: current folder).

Start it (stdio):  python mcp_tools_swebench.py
Start it (HTTP):   python mcp_tools_swebench.py --http --port 8001  ->  http://127.0.0.1:8001/mcp
Every path is relative to the repository root and can never leave it.
"""
import argparse
import os
import posixpath
import shlex
import subprocess

from mcp.server.fastmcp import FastMCP

CONTAINER_ENV = "SWEBENCH_CONTAINER"
REPO_DIR_ENV = "SWEBENCH_REPO_DIR"
CONTAINER_REPO = "/testbed"
# SWE-bench images install the project in a conda environment called "testbed"
CONTAINER_SETUP = "source /opt/miniconda3/bin/activate testbed >/dev/null 2>&1; "
MAX_LINES = 300                 # read_file: at most this many lines per call
MAX_ENTRIES = 200               # list_files: at most this many entries
MAX_MATCHES = 50                # search_code: at most this many results
MAX_OUTPUT_CHARS = 6000         # run_command / run_tests: longer outputs are shortened
COMMAND_TIMEOUT = 300           # seconds for run_command / run_tests
SKIPPED_DIRS = (".git", "__pycache__", ".venv", "node_modules", ".tox", "build", "dist")

server = FastMCP("swebench-tools", log_level="WARNING")


# ---------- Where the commands run: inside the container, or in a local folder ----------

def _container() -> str:
    return os.environ.get(CONTAINER_ENV, "")


def _local_repo() -> str:
    return os.path.realpath(os.environ.get(REPO_DIR_ENV, "."))


def _shell(command: str, stdin: str | None = None,
           timeout: float = COMMAND_TIMEOUT) -> subprocess.CompletedProcess[str]:
    """Run a bash command in the repository root (inside the container in Docker mode)."""
    container = _container()
    if container:
        args = ["docker", "exec", "-i", "-w", CONTAINER_REPO, container,
                "bash", "-c", CONTAINER_SETUP + command]
        cwd = None
    else:
        args, cwd = ["bash", "-c", command], _local_repo()
    try:
        return subprocess.run(args, input=stdin, capture_output=True, text=True,
                              timeout=timeout, cwd=cwd)
    except subprocess.TimeoutExpired:
        raise ValueError(f"the command took more than {timeout:.0f} s and was stopped") from None


def _shorten(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    """Keep the beginning and the end of a long output (errors and summaries are at the end)."""
    if len(text) <= limit:
        return text
    half = limit // 2
    return f"{text[:half]}\n[... {len(text) - limit} characters cut ...]\n{text[-half:]}"


def safe_path(path: str) -> str:
    """Normalize a path relative to the repository root; refuse anything that leaves it."""
    if path.startswith("/"):
        if path == CONTAINER_REPO or path.startswith(CONTAINER_REPO + "/"):
            path = posixpath.relpath(path, CONTAINER_REPO)     # accept /testbed/... too
        else:
            raise ValueError(f"'{path}' is outside the repository (use a path relative to it)")
    normalized = posixpath.normpath(path)
    if normalized == ".." or normalized.startswith("../"):
        raise ValueError(f"'{path}' is outside the repository")
    return normalized


def _read_text(path: str) -> str:
    """Whole content of a repository file."""
    result = _shell(f"cat -- {shlex.quote(path)}")
    if result.returncode != 0:
        raise ValueError(f"cannot read '{path}': {result.stderr.strip()}")
    return result.stdout


# ---------- Tools ----------

@server.tool()
def read_file(path: str, start_line: int = 1, end_line: int = 0) -> str:
    """Read a file of the repository, with line numbers.

    `path` is relative to the repository root. Use start_line/end_line to read a part
    of a long file (end_line 0 = until the end). At most 300 lines are returned per call.
    """
    path = safe_path(path)
    lines = _read_text(path).splitlines()
    first = max(start_line, 1)
    last = len(lines) if end_line <= 0 else min(end_line, len(lines))
    last = min(last, first + MAX_LINES - 1)
    numbered = [f"{n:5d} | {lines[n - 1]}" for n in range(first, last + 1)]
    return "\n".join(numbered + [f"[lines {first}-{last} of {len(lines)}]"])


@server.tool()
def list_files(path: str = ".") -> str:
    """List the files and folders inside a folder of the repository (folders end with '/')."""
    path = safe_path(path)
    result = _shell(f"ls -1Ap -- {shlex.quote(path)}")
    if result.returncode != 0:
        raise ValueError(f"cannot list '{path}': {result.stderr.strip()}")
    names = [n for n in result.stdout.splitlines()
             if not n.startswith(".") and n.rstrip("/") not in SKIPPED_DIRS]
    if len(names) > MAX_ENTRIES:
        names = names[:MAX_ENTRIES] + [f"[... {len(names) - MAX_ENTRIES} more]"]
    return "\n".join(names) if names else "(empty folder)"


@server.tool()
def search_code(pattern: str, path: str = ".") -> str:
    """Search a pattern (extended regular expression, like grep -E) in the .py files.

    Returns 'file:line: text' for each match (at most 50).
    """
    path = safe_path(path)
    excluded = " ".join(f"--exclude-dir={shlex.quote(d)}" for d in SKIPPED_DIRS)
    result = _shell(f"grep -rnE --include='*.py' {excluded} -e {shlex.quote(pattern)} "
                    f"-- {shlex.quote(path)} | head -n {MAX_MATCHES + 1}")
    lines = [line.removeprefix("./") for line in result.stdout.splitlines()]
    if not lines:
        return "No matches found" + (f" ({result.stderr.strip()})" if result.stderr.strip() else "")
    if len(lines) > MAX_MATCHES:
        lines = lines[:MAX_MATCHES] + [f"[stopped after {MAX_MATCHES} matches]"]
    return "\n".join(lines)


@server.tool()
def edit_file(path: str, old_text: str, new_text: str) -> str:
    """Replace `old_text` by `new_text` in a file of the repository.

    `old_text` must appear EXACTLY ONCE in the file (copy it with its indentation);
    include more surrounding lines if it appears several times.
    """
    path = safe_path(path)
    content = _read_text(path)
    count = content.count(old_text)
    if count == 0:
        raise ValueError("old_text was not found in the file (check spaces and indentation)")
    if count > 1:
        raise ValueError(f"old_text appears {count} times; include more lines to make it unique")
    result = _shell(f"cat > {shlex.quote(path)}", stdin=content.replace(old_text, new_text))
    if result.returncode != 0:
        raise ValueError(f"cannot write '{path}': {result.stderr.strip()}")
    return f"Edited {path}: 1 replacement"


def _require_container(tool: str) -> None:
    """Arbitrary commands only run inside the disposable container, never on the host."""
    if not _container():
        raise ValueError(f"{tool} is only available in Docker mode ({CONTAINER_ENV} is not set)")


@server.tool()
def run_command(command: str) -> str:
    """Run a shell command in the repository root (e.g. a python one-liner that reproduces the bug).

    Returns the exit code and the output (long outputs are shortened). Timeout: 300 s.
    """
    _require_container("run_command")
    result = _shell(command)
    return _shorten(f"exit code {result.returncode}\n{result.stdout}{result.stderr}")


@server.tool()
def run_tests(path: str) -> str:
    """Run the tests of one test file or folder of the repository (e.g. 'sympy/core/tests/test_symbol.py').

    Uses the project's own test runner (bin/test for sympy, pytest otherwise).
    Returns the exit code and the end of the output, where the summary is.
    """
    _require_container("run_tests")
    path = shlex.quote(safe_path(path))
    command = (f"if [ -x bin/test ]; then bin/test -C {path}; "
               f"else python -m pytest -q -x {path}; fi")
    result = _shell(command)
    return _shorten(f"exit code {result.returncode}\n{result.stdout}{result.stderr}")


@server.tool()
def get_patch() -> str:
    """The git diff of every change made so far to the repository files: this is the solution to submit."""
    result = _shell("git -c core.fileMode=false diff")
    if result.returncode != 0:
        raise ValueError(f"git diff failed: {result.stderr.strip()}")
    return result.stdout if result.stdout.strip() else "(no changes yet)"


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