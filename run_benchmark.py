"""Benchmark: run every model of models.json on every task, one agent run per (model, task).

    python run_benchmark.py --benchmark swebench
    python run_benchmark.py --benchmark mbpp --no-tools        # ablation: same tasks, no tools
    python run_benchmark.py --benchmark mbpp --dry-run         # only show the plan

Results: benchmark/results/<benchmark>/<variant>/<model>/<task_id>.json (+ .stderr.log).
With AGENT_MOCK_LLM=1 they go to benchmark/results-mock/ instead (pipeline check only).
Runs that already FINISHED are skipped, so the script can be launched again every day
until everything is done (the free tiers only allow a few runs per day).
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from core.model_config import DEFAULT_MODELS_CONFIG, load_models_config
from core.mock_llm import MOCK_ENV

REPO_ROOT = Path(__file__).resolve().parent
BENCHMARK_DIR = REPO_ROOT / "benchmark"
RUN_TIMEOUT_SECONDS = 1800          # safety net: the agent has its own (shorter) time limit
# Errors that mean "the LLM was not available", not "the agent failed": the run must be redone
UNFINISHED_ERRORS = ("LLM request failed", "Missing API key")


@dataclass
class ModelToRun:
    """One model of models.json with the provider data needed to call it."""
    provider: str
    model: str
    api_url: str
    key_env: str | None             # first environment variable that holds a key (None = no key)

    @property
    def folder(self) -> str:
        """Safe folder name: 'nvidia/nemotron-3:free' -> 'nvidia__nemotron-3_free'."""
        return re.sub(r"[^\w.-]", "_", self.model.replace("/", "__"))


def parse_args() -> argparse.Namespace:
    """Read the command-line options."""
    parser = argparse.ArgumentParser(description="Run every model on every benchmark task.")
    parser.add_argument("--benchmark", choices=["mbpp", "swebench"], required=True)
    parser.add_argument("--tasks-dir", type=Path, default=None,
                        help="Folder with one task JSON per task (default: benchmark/tasks/<benchmark>)")
    parser.add_argument("--models-config", type=Path, default=DEFAULT_MODELS_CONFIG)
    parser.add_argument("--models", nargs="*", default=None,
                        help="Only the models whose name contains one of these words")
    parser.add_argument("--no-tools", action="store_true",
                        help="MBPP ablation: run the agent without the MCP tools")
    parser.add_argument("--dry-run", action="store_true", help="Show the plan, run nothing")
    return parser.parse_args()


def models_to_run(config_path: Path, filters: list[str] | None) -> list[ModelToRun]:
    """The models of models.json (once each, in order), with the first key that exists."""
    config = load_models_config(config_path)
    models = []
    for entry in config.models:
        if filters and not any(word in entry.model for word in filters):
            continue
        provider = config.providers[entry.provider]
        key_env = next((env for env in provider.api_key_envs if os.getenv(env)), None)
        models.append(ModelToRun(entry.provider, entry.model, provider.api_url, key_env))
    return models


def is_finished(result_file: Path) -> bool:
    """True if this run already happened for real (a failed task also counts as finished)."""
    try:
        result = json.loads(result_file.read_text())
    except (OSError, ValueError):
        return False                        # missing or broken file: run it
    error = result.get("error") or ""
    return not error.startswith(UNFINISHED_ERRORS)


def run_one(benchmark: str, model: ModelToRun, task_file: Path, result_file: Path,
            no_tools: bool) -> dict:
    """Run the agent CLI once (in its own process) and return the result JSON."""
    command = [sys.executable, "-m", f"agent_{benchmark}",
               "--task-file", str(task_file), "--output", str(result_file),
               "--model-name", model.model, "--provider-url", model.api_url,
               "--api-key-env", model.key_env or "", "--no-fallback"]
    if no_tools:
        command.append("--no-tools")
    result_file.parent.mkdir(parents=True, exist_ok=True)
    log_file = result_file.with_suffix(".stderr.log")
    with log_file.open("w") as log:
        try:
            subprocess.run(command, cwd=REPO_ROOT, stdout=subprocess.DEVNULL, stderr=log,
                           timeout=RUN_TIMEOUT_SECONDS, check=False)
        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"run killed after {RUN_TIMEOUT_SECONDS} s"}
    try:
        return json.loads(result_file.read_text())
    except (OSError, ValueError):
        return {"success": False, "error": f"no result file (see {log_file.name})"}


def main() -> None:
    load_dotenv()
    args = parse_args()
    mock = os.getenv(MOCK_ENV) == "1"
    variant = "no-tools" if args.no_tools else "tools"
    tasks_dir = args.tasks_dir or BENCHMARK_DIR / "tasks" / args.benchmark
    task_files = sorted(tasks_dir.glob("*.json"))
    if not task_files:
        sys.exit(f"Error: no task files in {tasks_dir}")
    models = models_to_run(args.models_config, args.models)
    # mock runs go to their own folder, so they are never mistaken for real (finished) runs
    results_dir = BENCHMARK_DIR / ("results-mock" if mock else "results") / args.benchmark / variant

    print(f"Benchmark {args.benchmark} ({variant}): {len(models)} model(s) x "
          f"{len(task_files)} task(s){'  [MOCK LLM]' if mock else ''}")
    exhausted: set[str] = set()             # providers whose quota ran out during this launch
    counts = {"done": 0, "skipped": 0, "unfinished": 0}

    for model in models:
        for task_file in task_files:
            result_file = results_dir / model.folder / task_file.name
            label = f"{model.model} | {task_file.stem}"
            if is_finished(result_file):
                counts["skipped"] += 1
                print(f"  SKIP  {label} (already finished)")
                continue
            if (model.key_env is None and not mock) or model.provider in exhausted:
                counts["unfinished"] += 1
                reason = "no API key" if model.key_env is None else "quota used up"
                print(f"  WAIT  {label} ({reason}, will run another day)")
                continue
            if args.dry_run:
                print(f"  PLAN  {label}")
                continue

            start = time.perf_counter()
            result = run_one(args.benchmark, model, task_file, result_file, args.no_tools)
            elapsed = time.perf_counter() - start
            if is_finished(result_file):
                counts["done"] += 1
                status = "SUCCESS" if result.get("success") else "FAILED"
                print(f"  {status:7} {label} | iterations={result.get('iterations')} "
                      f"time={elapsed:.0f}s")
            else:                           # the LLM was not available: try again another day
                counts["unfinished"] += 1
                exhausted.add(model.provider)
                print(f"  WAIT  {label} ({(result.get('error') or '')[:80]})")

    print(f"Done: {counts['done']} run(s) now, {counts['skipped']} already finished, "
          f"{counts['unfinished']} left for another day. Results in {results_dir}")


if __name__ == "__main__":
    main()