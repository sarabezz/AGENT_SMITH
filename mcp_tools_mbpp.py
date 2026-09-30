"""MCP server with the MBPP tools.

Start it (stdio):  python mcp_tools_mbpp.py
Start it (HTTP):   python mcp_tools_mbpp.py --http --port 8000   ->  http://127.0.0.1:8000/mcp
The current task is read from the file given in the MBPP_TASK_FILE environment variable.
"""
import argparse
import ast
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from pydantic import ValidationError

from core.models_public import MBPPTaskInput, SandboxConfig
from core.sandbox import Sandbox

TASK_FILE_ENV = "MBPP_TASK_FILE"
SANDBOX_CONFIG_FILE = Path(__file__).resolve().parent / "sandbox_template.json"

server = FastMCP("mbpp-tools")


def load_task() -> MBPPTaskInput:
    """Read the current MBPP task from the file named in MBPP_TASK_FILE."""
    path = os.environ.get(TASK_FILE_ENV)
    if not path:
        raise ValueError(f"no MBPP task loaded: the environment variable {TASK_FILE_ENV} is not set")
    return MBPPTaskInput.model_validate_json(Path(path).read_text())


def _actual_value_code(test: str) -> str | None:
    """For a test like `assert f(x) == y`, return code that prints what f(x) really returned."""
    try:
        node = ast.parse(test).body[0]
    except (SyntaxError, IndexError):
        return None
    if (isinstance(node, ast.Assert) and isinstance(node.test, ast.Compare)
            and len(node.test.ops) == 1 and isinstance(node.test.ops[0], ast.Eq)):
        left = ast.get_source_segment(test, node.test.left)
        return f"print(repr({left}))" if left else None
    return None


def _run_one_test(sandbox: Sandbox, test: str) -> tuple[bool, str]:
    """Run one test in the sandbox. Returns (passed, explanation of the failure)."""
    output = sandbox.run(test)
    if sandbox.last_run_ok:
        return True, ""
    reason = output.strip().splitlines()[-1] if output.strip() else "failed"
    actual_code = _actual_value_code(test)
    if actual_code is not None:
        actual = sandbox.run(actual_code)
        if sandbox.last_run_ok:
            reason += f" (your function returned {actual.strip()})"
    return False, reason


@server.tool()
def run_tests(code: str) -> str:
    """Run the official tests of the current MBPP task against your code.

    `code` must contain the complete function (and any imports it needs).
    Returns how many tests passed and why each failed test failed.
    """
    try:
        task = load_task()
        config = SandboxConfig.model_validate_json(SANDBOX_CONFIG_FILE.read_text())
    except (OSError, ValueError, ValidationError) as exc:
        return f"Error: {exc}"

    sandbox = Sandbox(config)                  # the tests run in OUR secure sandbox, never directly
    try:
        output = sandbox.run("\n".join(task.test_imports + [code]))
        if not sandbox.last_run_ok:
            return f"Your code could not run, so no test was executed:\n{output}"
        lines: list[str] = []
        passed = 0
        for test in task.test_list:
            ok, reason = _run_one_test(sandbox, test)
            if ok:
                passed += 1
                lines.append(f"PASSED: {test}")
            else:
                lines.append(f"FAILED: {test}\n        -> {reason}")
        return "\n".join([f"{passed}/{len(task.test_list)} tests passed"] + lines)
    finally:
        sandbox.close()


@server.resource("mbpp://task")
def task_description() -> str:
    """The current MBPP task: description, function signature and tests."""
    try:
        task = load_task()
    except (OSError, ValueError, ValidationError) as exc:
        return f"Error: {exc}"
    return "\n".join([f"Task: {task.task_definition}", f"Signature: {task.function_definition}",
                      "Tests:"] + task.test_list)


@server.prompt()
def solve_mbpp_task() -> str:
    """Short method to solve an MBPP task with these tools."""
    return ("Write the function with the exact signature, call run_tests(code) with its full source, "
            "read which tests fail and why, fix the code, and submit it with final_answer "
            "once every test passes.")


def main() -> None:
    parser = argparse.ArgumentParser(description="MCP server with the MBPP tools.")
    parser.add_argument("--http", action="store_true", help="Serve over streamable HTTP instead of stdio")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if args.http:
        server.settings.port = args.port
        server.run(transport="streamable-http")
    else:
        server.run()                          # stdio


if __name__ == "__main__":
    main()