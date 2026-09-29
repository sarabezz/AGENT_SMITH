"""Imitate the MBPP exam: N random tasks -> dump -> agent -> validate."""
import subprocess
from pathlib import Path

N_TASKS = 5
MODEL = "qwen/qwen3.8-27b:free"
PROVIDER_URL = "https://openrouter.ai/api/v1"

ROOT = Path(__file__).resolve().parent.parent      # .../agent_smith
MOULINETTE = ROOT.parent / "moulinette"
BATCH_DIR = ROOT.parent / "cache" / "batch"


def run(cmd: list[str], cwd: Path) -> str:
    """Run a terminal command in the folder `cwd` and return everything it printed."""
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return result.stdout + result.stderr


def find_line(text: str, start: str) -> str:
    """Return the first line of `text` that starts with `start`, or '' if there is none."""
    for line in text.splitlines():
        if line.startswith(start):
            return line.strip()
    return ""


def main() -> None:
    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    passed = 0

    for i in range(1, N_TASKS + 1):
        task_file = BATCH_DIR / f"task_{i}.json"
        solution_file = BATCH_DIR / f"solution_{i}.json"

        # 1. DUMP: the moulinette picks a random task
        run(["uv", "run", "moulinette_eval", "dump", "mbpp", "--output", str(task_file)], MOULINETTE)

        # 2. RUN: our agent solves it
        agent_out = run(["uv", "run", "python", "-m", "agent_mbpp",
                         "--task-file", str(task_file), "--output", str(solution_file),
                         "--model-name", MODEL, "--provider-url", PROVIDER_URL], ROOT)

        # 3. VALIDATE: the moulinette checks it
        validate_out = run(["uv", "run", "moulinette_eval", "validate", "mbpp",
                            str(task_file), str(solution_file)], MOULINETTE)

        ok = "Overall: PASSED" in validate_out
        if ok:
            passed += 1
        print(f"\n[{i}/{N_TASKS}] {'PASSED' if ok else 'FAILED'}")
        print("   agent:   ", find_line(agent_out, "Task"))
        print("   validate:", find_line(validate_out, "Correctness:"),
              "|", find_line(validate_out, "Metrics:"))

    print(f"\nResult: {passed}/{N_TASKS} passed (the exam needs 4/5)")


if __name__ == "__main__":
    main()