"""Connect to the MBPP MCP server through the client, like the sandbox will do."""
import sys

from mcp_client import McpClientManager

WRONG = "def differ_At_One_Bit_Pos(a, b):\n    return a != b"


def main() -> None:
    manager = McpClientManager(stdio_cmd=[sys.executable, "mcp_tools_mbpp.py"],
                               env={"MBPP_TASK_FILE": "../cache/task6.json"})
    try:
        print("TOOLS:", [tool.name for tool in manager.tools])
        for tool in manager.tools:
            print(f"  {tool.name}: {tool.description}")
            print(f"  parameters: {tool.inputSchema}")
        print("\n--- run_tests(WRONG) ---")
        print(manager.call_tool("run_tests", {"code": WRONG}))
        print("\n--- a tool that does not exist ---")
        print(manager.call_tool("does_not_exist", {}))
    finally:
        manager.close()
        print("\nconnection closed")


if __name__ == "__main__":
    main()