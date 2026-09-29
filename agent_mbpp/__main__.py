"""CLI: python -m agent_mbpp --task-file task.json --output solution.json --model-name ... --provider-url ..."""
import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from pydantic import ValidationError

from agent_mbpp.prompts import SYSTEM_PROMPT, build_task_prompt
from core.agent import Agent, AgentLimits
from core.llm import LLMClient
from core.models_public import MBPPTaskInput, SolutionOutput

MAX_TOKENS_PER_CALL = 400


def parse_args() -> argparse.Namespace:
    """Read the command-line options."""
    parser = argparse.ArgumentParser(description="Solve one MBPP task with the agent.")
    parser.add_argument("--task-file", required=True, type=Path, help="Task JSON from the moulinette")
    parser.add_argument("--output", required=True, type=Path, help="Where to write solution.json")
    parser.add_argument("--model-name", required=True, help="e.g. qwen/qwen3.8-27b:free")
    parser.add_argument("--provider-url", required=True, help="e.g. https://openrouter.ai/api/v1")
    parser.add_argument("--api-key-env", default="OPENROUTER_API_KEY",
                        help="Name of the environment variable that holds the API key")
    parser.add_argument("--max-iterations", type=int, default=10)
    return parser.parse_args()


def failed_output(task_id: str, error: str) -> SolutionOutput:
    """A valid SolutionOutput for when the agent could not even start."""
    return SolutionOutput(
        task_id=task_id, benchmark="mbpp", success=False, solution="",
        iterations=0, total_requests=0, total_input_tokens=0, total_output_tokens=0,
        total_time_seconds=0.0, system_prompt=SYSTEM_PROMPT, error=error,
    )


def solve(args: argparse.Namespace) -> SolutionOutput:
    """Load the task, build the agent and run it."""
    try:
        task = MBPPTaskInput.model_validate_json(args.task_file.read_text())
    except (OSError, ValidationError) as exc:
        return failed_output("unknown", f"Could not read task file: {exc}")

    api_key = os.getenv(args.api_key_env)
    if not api_key:
        return failed_output(str(task.task_id), f"Missing API key: {args.api_key_env} is not set")

    llm = LLMClient(
        api_url=args.provider_url,
        api_key=api_key,
        model_name=args.model_name,
        max_tokens=MAX_TOKENS_PER_CALL,
        stop=["<end_code>"],
        extra_body={"reasoning": {"enabled": False}},
    )
    agent = Agent(llm=llm, system_prompt=SYSTEM_PROMPT, benchmark="mbpp",
                  limits=AgentLimits(max_iterations=args.max_iterations))
    return agent.run(task_id=str(task.task_id), task_prompt=build_task_prompt(task))


def main() -> None:
    load_dotenv()
    args = parse_args()
    result = solve(args)
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result.model_dump_json(indent=2))
    except OSError as exc:
        print(f"Error: could not write {args.output}: {exc}", file=sys.stderr)
        sys.exit(1)

    status = "SUCCESS" if result.success else f"FAILED ({result.error})"
    print(f"Task {result.task_id}: {status} | iterations={result.iterations} "
          f"input_tokens={result.total_input_tokens} output_tokens={result.total_output_tokens} "
          f"time={result.total_time_seconds:.1f}s")
    print(f"Solution written to {args.output}")


if __name__ == "__main__":
    main()