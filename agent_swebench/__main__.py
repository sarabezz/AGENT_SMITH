"""CLI: python -m agent_swebench --task-file task.json --output solution.json --model-name ... --provider-url ..."""
import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv
from pydantic import ValidationError

from agent_swebench.prompts import SYSTEM_PROMPT, build_system_prompt, build_task_prompt
from core.agent import Agent, AgentLimits
from core.container import ContainerError, TaskContainer
from core.llm_router import NoCandidateError
from core.llm_setup import build_llm, is_mock
from core.model_config import DEFAULT_MODELS_CONFIG
from core.models_public import SandboxConfig, SolutionOutput, SWEBenchTaskInput
from core.tool_bridge import tool_specs_from, tools_manual
from mcp_client import McpClientManager

MAX_TOKENS_PER_CALL = 1000
MAX_OBSERVATION_CHARS = 6000            # tool outputs (file parts, test logs) are longer than in MBPP
KEEP_FULL_OBSERVATIONS = 2              # older observations are shortened (saves tokens)
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SANDBOX_CONFIG = REPO_ROOT / "sandbox_template.json"
MCP_SERVER_FILE = REPO_ROOT / "mcp_tools_swebench.py"
DEFAULT_LIMITS = AgentLimits(max_iterations=30, max_input_tokens=300_000,
                             max_output_tokens=10_000, max_time_seconds=900.0,
                             max_observation_chars=MAX_OBSERVATION_CHARS,
                             keep_full_observations=KEEP_FULL_OBSERVATIONS)


def parse_args() -> argparse.Namespace:
    """Read the command-line options (the exam script passes all of them)."""
    parser = argparse.ArgumentParser(description="Fix one SWE-bench issue with the agent.")
    parser.add_argument("--task-file", required=True, type=Path, help="Task JSON from the moulinette")
    parser.add_argument("--output", required=True, type=Path, help="Where to write solution.json")
    parser.add_argument("--model-name", required=True, help="e.g. nvidia/nemotron-3-super-120b-a12b:free")
    parser.add_argument("--provider-url", required=True, help="e.g. https://openrouter.ai/api/v1")
    parser.add_argument("--api-key-env", default="OPENROUTER_API_KEY",
                        help="Name of the environment variable that holds the API key")
    parser.add_argument("--max-iterations", type=int, default=DEFAULT_LIMITS.max_iterations)
    parser.add_argument("--max-input-tokens", type=int, default=DEFAULT_LIMITS.max_input_tokens)
    parser.add_argument("--max-output-tokens", type=int, default=DEFAULT_LIMITS.max_output_tokens)
    parser.add_argument("--timeout", type=float, default=DEFAULT_LIMITS.max_time_seconds,
                        help="Maximum wall-clock seconds for the whole task")
    parser.add_argument("--sandbox-config", type=Path, default=DEFAULT_SANDBOX_CONFIG,
                        help="Sandbox configuration JSON (default: sandbox_template.json)")
    parser.add_argument("--models-config", type=Path, default=DEFAULT_MODELS_CONFIG,
                        help="Models configuration JSON with the fallback list (default: models.json)")
    parser.add_argument("--no-fallback", action="store_true",
                        help="Use ONLY the model given on the command line (e.g. for the benchmark)")
    return parser.parse_args()


def failed_output(task_id: str, error: str) -> SolutionOutput:
    """A valid SolutionOutput for when the agent could not even start."""
    return SolutionOutput(
        task_id=task_id, benchmark="swebench", success=False, solution="",
        iterations=0, total_requests=0, total_input_tokens=0, total_output_tokens=0,
        total_time_seconds=0.0, system_prompt=SYSTEM_PROMPT, error=error,
    )


def run_agent(args: argparse.Namespace, task: SWEBenchTaskInput, llm: object,
              limits: AgentLimits, sandbox_config: SandboxConfig,
              mcp_client: McpClientManager | None) -> SolutionOutput:
    """Run the agent loop; the submitted patch is replaced by the REAL git diff of the container."""
    manual = tools_manual(tool_specs_from(mcp_client.tools)) if mcp_client else ""
    agent = Agent(llm=llm, system_prompt=build_system_prompt(manual), benchmark="swebench",
                  limits=limits, sandbox_config=sandbox_config, mcp_client=mcp_client)
    result = agent.run(task_id=task.instance_id, task_prompt=build_task_prompt(task))
    if mcp_client is None:
        return result
    patch = mcp_client.call_tool("get_patch", {})
    if not patch.startswith("diff --git"):           # nothing was changed in /testbed
        return result
    if result.success:                               # the truth is what changed in /testbed
        return result.model_copy(update={"solution": patch})
    # Auto-submit: the budget ran out but the repository WAS changed. The diff is submitted
    # so it can be graded; success stays False (the model never called final_answer).
    note = "auto-submitted the current git diff (final_answer was never called)"
    return result.model_copy(update={"solution": patch,
                                    "error": f"{result.error} | {note}" if result.error else note})


def solve(args: argparse.Namespace) -> SolutionOutput:
    """Load the task and the configs, start the container and the tools, run the agent."""
    try:
        task = SWEBenchTaskInput.model_validate_json(args.task_file.read_text())
    except (OSError, ValidationError) as exc:
        return failed_output("unknown", f"Could not read task file: {exc}")

    try:
        sandbox_config = SandboxConfig.model_validate_json(args.sandbox_config.read_text())
    except (OSError, ValidationError) as exc:
        return failed_output(task.instance_id, f"Could not read sandbox config: {exc}")

    try:
        llm = build_llm(args, max_tokens=MAX_TOKENS_PER_CALL)
    except (OSError, ValidationError) as exc:
        return failed_output(task.instance_id, f"Could not read models config: {exc}")
    except NoCandidateError as exc:
        return failed_output(task.instance_id, f"Missing API key: {exc}")

    limits = AgentLimits(
        max_iterations=args.max_iterations,
        max_input_tokens=args.max_input_tokens,
        max_output_tokens=args.max_output_tokens,
        max_time_seconds=args.timeout,
        max_observation_chars=MAX_OBSERVATION_CHARS,
        keep_full_observations=KEEP_FULL_OBSERVATIONS,
    )

    if is_mock(args):                       # fake LLM: no container, no tools (pipeline check only)
        return run_agent(args, task, llm, limits, sandbox_config, mcp_client=None)

    try:
        with TaskContainer(task.docker_image, task.instance_id) as container:
            mcp_client = McpClientManager(
                stdio_cmd=[sys.executable, str(MCP_SERVER_FILE)],
                env={"SWEBENCH_CONTAINER": container.name},   # the note: which container to use
            )
            try:
                return run_agent(args, task, llm, limits, sandbox_config, mcp_client)
            finally:
                mcp_client.close()
    except ContainerError as exc:
        return failed_output(task.instance_id, f"Docker error: {exc}")


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