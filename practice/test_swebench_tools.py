"""Phase 8.3: the SWE-bench tools working inside a real container (sympy__sympy-23534)."""
import os
import subprocess

IMAGE = "swebench/sweb.eval.x86_64.sympy_1776_sympy-23534:latest"
CONTAINER = "sympy__sympy-23534"
REPRODUCE = ('python -c "import sympy as smp; q, u = smp.symbols((\'q:2\', \'u:2\'), '
             'cls=smp.Function); print(type(q[0]))"')


def main() -> None:
    subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True)
    subprocess.run(["docker", "run", "-d", "--name", CONTAINER, IMAGE, "sleep", "infinity"],
                   check=True, capture_output=True)
    os.environ["SWEBENCH_CONTAINER"] = CONTAINER        # the note: which container to use
    import mcp_tools_swebench as tools                  # imported AFTER the note is set
    try:
        print("--- 1. reproduce the bug ---")
        print(tools.run_command(REPRODUCE))
        print("--- 2. where is symbols() defined? ---")
        print(tools.search_code(r"^def symbols", "sympy/core"))
        print("--- 3. list a folder ---")
        print(tools.list_files("sympy/core")[:200], "...")
        print("--- 4. read the start of symbols() ---")
        line = int(tools.search_code(r"^def symbols", "sympy/core").split(":")[1])
        print(tools.read_file("sympy/core/symbol.py", line, line + 5))
        print("--- 5. patch before any change ---")
        print(tools.get_patch())
        print("--- 6. run the existing tests of test_symbol.py (can take a minute) ---")
        print(tools.run_tests("sympy/core/tests/test_symbol.py")[-600:])
    finally:
        subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True)
        print("container removed")


if __name__ == "__main__":
    main()