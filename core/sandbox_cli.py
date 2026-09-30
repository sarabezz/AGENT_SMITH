"""Interactive sandbox: `uv run sandbox [config.json]` — type Python code, it runs in the secure sandbox."""
import argparse
import ast
import codeop
import sys
from pathlib import Path

from pydantic import ValidationError

from core.models_public import SandboxConfig
from core.sandbox import Sandbox

EXIT_COMMANDS = ("exit", "exit()", "quit", "quit()")
PROMPT = ">>> "
CONTINUATION = "... "


def parse_args() -> argparse.Namespace:
    """Read the command-line options."""
    parser = argparse.ArgumentParser(prog="sandbox",
                                     description="Interactive secure sandbox for LLM-generated code.")
    parser.add_argument("config", nargs="?", type=Path,
                        help="Sandbox configuration JSON (default: the secure empty configuration)")
    return parser.parse_args()


def load_config(path: Path | None) -> SandboxConfig:
    """Load the configuration file, or return the secure default configuration."""
    if path is None:
        return SandboxConfig()
    return SandboxConfig.model_validate_json(path.read_text())


def print_banner(config: SandboxConfig) -> None:
    """Show which rules are active."""
    allowed = ", ".join(config.authorized_imports) or "none"
    directories = ", ".join(config.allowed_directories) or "none"
    print("Secure sandbox. Type Python code; an empty line ends a multi-line block.")
    print(f"  imports allowed : {allowed}")
    print(f"  directories     : {directories}")
    print(f"  limits          : {config.max_execution_time_seconds} s, {config.max_memory_mb} MB, no network")
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

    print_banner(config)
    sandbox = Sandbox(config)
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
        print("Sandbox closed.")


if __name__ == "__main__":
    main()