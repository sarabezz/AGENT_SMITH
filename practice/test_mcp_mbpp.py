"""Call the MBPP tool directly (without agent, LLM or MCP) to check it works on its own."""
import os

os.environ["MBPP_TASK_FILE"] = "../cache/task6.json"

from mcp_tools_mbpp import run_tests  # noqa: E402  (must be imported after setting the variable)

GOOD = "def differ_At_One_Bit_Pos(a, b):\n    x = a ^ b\n    return x != 0 and x & (x - 1) == 0"
WRONG = "def differ_At_One_Bit_Pos(a, b):\n    return a != b"
CRASHES = "def differ_At_One_Bit_Pos(a, b):\n    return x"
SYNTAX_ERROR = "def differ_At_One_Bit_Pos(a, b:"


def main() -> None:
    for name, code in [("GOOD", GOOD), ("WRONG", WRONG), ("CRASHES", CRASHES),
                       ("SYNTAX ERROR", SYNTAX_ERROR)]:
        print(f"===== {name} =====")
        print(run_tests(code))
        print()


if __name__ == "__main__":
    main()
