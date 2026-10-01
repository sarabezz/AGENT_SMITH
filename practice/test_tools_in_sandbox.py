"""Phase 6.4: the MCP tools work inside the sandbox as normal functions."""
import sys

from core.sandbox import Sandbox
from mcp_client import McpClientManager

WRONG = '''def differ_At_One_Bit_Pos(a, b):
    return a != b'''

LLM_CODE = f'''code = """{WRONG}"""
result = run_tests(code)
print(result)
print("first line:", result.splitlines()[0])
'''


def main() -> None:
    task_file = sys.argv[1]
    client = McpClientManager(stdio_cmd=[sys.executable, "mcp_tools_mbpp.py"],
                              env={"MBPP_TASK_FILE": task_file})
    sandbox = Sandbox(mcp_client=client)
    try:
        print("--- 1. tool called from LLM code ---")
        print(sandbox.run(LLM_CODE))
        print("--- 2. wrong call (missing argument) ---")
        print(sandbox.run("run_tests()"))
        print("--- 3. the sandbox is still protected ---")
        print(sandbox.run("import os"))
    finally:
        sandbox.close()
        client.close()


if __name__ == "__main__":
    main()