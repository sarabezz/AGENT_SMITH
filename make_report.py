"""Benchmark report generator: reads every run of run_benchmark.py and builds the tables.

    python make_report.py                 # tables from the results (+ cached validations)
    python make_report.py --validate      # also check correctness with the moulinette (slow)
    python make_report.py --mock          # use benchmark/results-mock/ (pipeline check)

For each run it reads <task>.json (the SolutionOutput). With --validate it runs
`moulinette_eval validate` and caches the verdict in <task>.validation.json, so a run is
only validated again if its solution changed. Output: benchmark/RESULTS.md (generated,
never edit it by hand; the written conclusions go in BENCHMARK_REPORT.md).
"""
import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from statistics import mean

from run_benchmark import is_finished

REPO_ROOT = Path(__file__).resolve().parent
BENCHMARK_DIR = REPO_ROOT / "benchmark"
DEFAULT_MOULINETTE = REPO_ROOT.parent / "moulinette"
VALIDATION_SUFFIX = ".validation.json"
VALIDATE_TIMEOUT_SECONDS = 1800      # SWE-bench validation starts a container and runs tests
AUTO_SUBMIT_MARK = "auto-submitted"


@dataclass
class Run:
    """One (model, task) run with the numbers the tables need."""
    benchmark: str
    variant: str
    model: str
    task: str
    submitted: bool                 # the agent called final_answer
    auto_submitted: bool            # SWE-bench: the diff was submitted for it
    correct: bool | None            # moulinette verdict (None = not validated yet)
    iterations: int
    requests: int
    input_tokens: int
    output_tokens: int
    seconds: float
    max_step_input: int             # biggest single request (how much the history grew)
    avg_request_ms: float


def parse_args() -> argparse.Namespace:
    """Read the command-line options."""
    parser = argparse.ArgumentParser(description="Build the benchmark tables.")
    parser.add_argument("--validate", action="store_true",
                        help="Check correctness with the moulinette (only runs not validated yet)")
    parser.add_argument("--moulinette-path", type=Path, default=DEFAULT_MOULINETTE)
    parser.add_argument("--mock", action="store_true", help="Read benchmark/results-mock/ instead")
    parser.add_argument("--output", type=Path, default=BENCHMARK_DIR / "RESULTS.md")
    return parser.parse_args()


def result_files(results_dir: Path) -> list[Path]:
    """Every run file: results/<benchmark>/<variant>/<model>/<task>.json (not the caches)."""
    return sorted(p for p in results_dir.glob("*/*/*/*.json")
                  if not p.name.endswith(VALIDATION_SUFFIX))


def cached_verdict(result_file: Path) -> bool | None:
    """The cached moulinette verdict, if it is newer than the solution file."""
    cache = result_file.with_name(result_file.stem + VALIDATION_SUFFIX)
    if not cache.exists() or cache.stat().st_mtime < result_file.stat().st_mtime:
        return None
    try:
        return bool(json.loads(cache.read_text())["correct"])
    except (OSError, ValueError, KeyError):
        return None


def validate(benchmark: str, task_file: Path, result_file: Path, moulinette: Path) -> bool | None:
    """Run the moulinette on one solution and cache the verdict. None if it could not run."""
    command = ["uv", "run", "moulinette_eval", "validate", benchmark,
               str(task_file.resolve()), str(result_file.resolve())]
    try:
        done = subprocess.run(command, cwd=moulinette, capture_output=True, text=True,
                              timeout=VALIDATE_TIMEOUT_SECONDS, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"  could not validate {result_file.name}: {exc}", file=sys.stderr)
        return None
    lines = (done.stdout + done.stderr).strip().splitlines()
    verdict_line = next((line for line in reversed(lines) if "Overall:" in line), "")
    if not verdict_line:
        print(f"  no verdict for {result_file.name}: {lines[-1:] or 'no output'}", file=sys.stderr)
        return None
    correct = "PASSED" in verdict_line
    cache = result_file.with_name(result_file.stem + VALIDATION_SUFFIX)
    cache.write_text(json.dumps({"correct": correct, "detail": verdict_line.strip()}))
    return correct


def load_run(result_file: Path, correct: bool | None) -> Run:
    """Read one SolutionOutput and keep the numbers for the tables."""
    data = json.loads(result_file.read_text())
    steps = data.get("steps") or []
    model_dir, variant_dir, benchmark_dir = result_file.parents[0], result_file.parents[1], result_file.parents[2]
    model = steps[-1]["model_name"] if steps else model_dir.name
    return Run(
        benchmark=benchmark_dir.name, variant=variant_dir.name, model=model, task=result_file.stem,
        submitted=bool(data.get("success")),
        auto_submitted=AUTO_SUBMIT_MARK in (data.get("error") or ""),
        correct=correct,
        iterations=data.get("iterations", 0),
        requests=data.get("total_requests", 0),
        input_tokens=data.get("total_input_tokens", 0),
        output_tokens=data.get("total_output_tokens", 0),
        seconds=data.get("total_time_seconds", 0.0),
        max_step_input=max((s.get("input_tokens", 0) for s in steps), default=0),
        avg_request_ms=mean(s.get("request_time_ms", 0) for s in steps) if steps else 0.0,
    )


def verdict_text(correct: bool | None) -> str:
    return {True: "✅", False: "❌", None: "?"}[correct]


def summary_table(runs: list[Run]) -> list[str]:
    """One row per model: how many runs were submitted / correct, and the averages."""
    lines = ["| Model | Runs | Submitted | Correct | Avg iterations | Avg input tokens "
             "| Avg output tokens | Avg time (s) |",
             "|---|---|---|---|---|---|---|---|"]
    for model in sorted({r.model for r in runs}):
        group = [r for r in runs if r.model == model]
        validated = [r for r in group if r.correct is not None]
        correct = f"{sum(r.correct for r in validated)}/{len(validated)}" if validated else "?"
        if len(validated) < len(group):
            correct += f" ({len(group) - len(validated)} not validated)"
        lines.append(f"| {model} | {len(group)} | {sum(r.submitted for r in group)}/{len(group)} "
                     f"| {correct} | {mean(r.iterations for r in group):.1f} "
                     f"| {mean(r.input_tokens for r in group):,.0f} "
                     f"| {mean(r.output_tokens for r in group):,.0f} "
                     f"| {mean(r.seconds for r in group):.1f} |")
    return lines


def detail_table(runs: list[Run]) -> list[str]:
    """One row per run, with the per-step (intermediary) metrics."""
    lines = ["| Model | Task | Submitted | Correct | Iterations | Requests | Input tokens "
             "| Output tokens | Biggest request (tokens) | Avg request (ms) | Time (s) |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(runs, key=lambda r: (r.model, r.task)):
        submitted = "auto" if r.auto_submitted else ("yes" if r.submitted else "no")
        lines.append(f"| {r.model} | {r.task} | {submitted} | {verdict_text(r.correct)} "
                     f"| {r.iterations} | {r.requests} | {r.input_tokens:,} | {r.output_tokens:,} "
                     f"| {r.max_step_input:,} | {r.avg_request_ms:,.0f} | {r.seconds:.1f} |")
    return lines


def ablation_table(runs: list[Run]) -> list[str]:
    """Models run in BOTH variants (tools / no-tools): the effect of the tools."""
    lines = ["| Model | Variant | Correct | Avg iterations | Avg input tokens |",
             "|---|---|---|---|---|"]
    models = sorted({r.model for r in runs if r.variant == "tools"}
                    & {r.model for r in runs if r.variant == "no-tools"})
    for model in models:
        for variant in ("tools", "no-tools"):
            group = [r for r in runs if r.model == model and r.variant == variant]
            validated = [r for r in group if r.correct is not None]
            correct = f"{sum(r.correct for r in validated)}/{len(validated)}" if validated else "?"
            lines.append(f"| {model} | {variant} | {correct} | "
                         f"{mean(r.iterations for r in group):.1f} | "
                         f"{mean(r.input_tokens for r in group):,.0f} |")
    return lines if models else []


def build_report(runs: list[Run]) -> str:
    """The whole RESULTS.md text."""
    out = ["# Benchmark results (generated by make_report.py, do not edit)", "",
           "Submitted = the agent called final_answer (`auto` = SWE-bench diff auto-submitted). "
           "Correct = moulinette verdict (? = not validated yet).", ""]
    for benchmark in sorted({r.benchmark for r in runs}):
        for variant in sorted({r.variant for r in runs if r.benchmark == benchmark}):
            group = [r for r in runs if r.benchmark == benchmark and r.variant == variant]
            out += [f"## {benchmark} ({variant})", "", "### Per model", ""]
            out += summary_table(group) + ["", "### Per run", ""]
            out += detail_table(group) + [""]
        ablation = ablation_table([r for r in runs if r.benchmark == benchmark])
        if ablation:
            out += [f"## {benchmark}: ablation (with vs. without tools)", ""] + ablation + [""]
    return "\n".join(out)


def main() -> None:
    args = parse_args()
    results_dir = BENCHMARK_DIR / ("results-mock" if args.mock else "results")
    files = result_files(results_dir)
    if not files:
        sys.exit(f"Error: no results in {results_dir}")

    runs = []
    unfinished = 0
    for result_file in files:
        if not is_finished(result_file):        # the LLM was never available: not a real result
            unfinished += 1
            continue
        correct = cached_verdict(result_file)
        if correct is None and args.validate:
            benchmark = result_file.parents[2].name
            task_file = BENCHMARK_DIR / "tasks" / benchmark / result_file.name
            print(f"validating {benchmark} | {result_file.parent.name} | {result_file.stem} ...")
            correct = validate(benchmark, task_file, result_file, args.moulinette_path)
        runs.append(load_run(result_file, correct))

    args.output.write_text(build_report(runs))
    not_validated = sum(r.correct is None for r in runs)
    print(f"{len(runs)} run(s) -> {args.output}"
          + (f" ({not_validated} not validated: use --validate)" if not_validated else "")
          + (f" ({unfinished} unfinished run(s) left out)" if unfinished else ""))


if __name__ == "__main__":
    main()