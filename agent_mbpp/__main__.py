"""CLI: python -m agent_mbpp --task-file task.json --output solution.json --model-name ... --provider-url ..."""
import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from pydantic import ValidationError

from agent_mbpp.prompts import SYSTEM_PROMPT, build_system_prompt, build_task_prompt
from core.agent import Agent, AgentLimits
from core.llm_router import LLMRouter, NoCandidateError
from core.mock_llm import MOCK_ENV, MOCK_NAME, MockLLM
from core.model_config import (
    DEFAULT_MODELS_CONFIG,
    Candidate,
    ModelsConfig,
    build_candidates,
    load_models_config,
)
from core.models_public import MBPPTaskInput, SandboxConfig, SolutionOutput
from core.tool_bridge import tool_specs_from, tools_manual
from mcp_client import McpClientManager

MAX_TOKENS_PER_CALL = 400
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SANDBOX_CONFIG = REPO_ROOT / "sandbox_template.json"
MCP_SERVER_FILE = REPO_ROOT / "mcp_tools_mbpp.py"
DEFAULT_LIMITS = AgentLimits()          # MBPP limits checked by the moulinette


def parse_args() -> argparse.Namespace:
    """Read the command-line options (the exam script passes all of them)."""
    parser = argparse.ArgumentParser(description="Solve one MBPP task with the agent.")
    parser.add_argument("--task-file", required=True, type=Path, help="Task JSON from the moulinette")
    parser.add_argument("--output", required=True, type=Path, help="Where to write solution.json")
    parser.add_argument("--model-name", required=True, help="e.g. qwen/qwen3.8-27b:free")
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
    parser.add_argument("--no-tools", action="store_true",
                        help="Do not start the MCP server (the agent checks its code with asserts)")
    return parser.parse_args()


def failed_output(task_id: str, error: str) -> SolutionOutput:
    """A valid SolutionOutput for when the agent could not even start."""
    return SolutionOutput(
        task_id=task_id, benchmark="mbpp", success=False, solution="",
        iterations=0, total_requests=0, total_input_tokens=0, total_output_tokens=0,
        total_time_seconds=0.0, system_prompt=SYSTEM_PROMPT, error=error,
    )


def command_line_candidate(args: argparse.Namespace, config: ModelsConfig) -> Candidate | None:
    """The model given with --model-name/--provider-url, if its API key exists.

    Its settings (provider name, extra_body) are taken from models.json when the same
    provider URL and model appear there.
    """
    api_key = os.getenv(args.api_key_env, "")
    if not api_key:
        return None
    provider_name, extra_body = "command-line", {}
    for name, provider in config.providers.items():
        if provider.api_url.rstrip("/") == args.provider_url.rstrip("/"):
            provider_name = name
            for entry in config.models:
                if entry.provider == name and entry.model == args.model_name:
                    extra_body = entry.extra_body
    return Candidate(provider_name, args.model_name, args.provider_url, api_key,
                     args.api_key_env, extra_body)


def build_llm(args: argparse.Namespace) -> LLMRouter | MockLLM:
    """The command-line model first, then (unless --no-fallback) the models.json list.

    With AGENT_MOCK_LLM=1 (or --provider-url mock) a fake LLM is used: no API key needed.
    """
    if os.getenv(MOCK_ENV) == "1" or args.provider_url == MOCK_NAME:
        return MockLLM(max_tokens=MAX_TOKENS_PER_CALL)
    config = load_models_config(args.models_config)
    candidates: list[Candidate] = []
    first = command_line_candidate(args, config)
    if first is not None:
        candidates.append(first)
    if not args.no_fallback:
        for candidate in build_candidates(config):
            already_there = any(c.api_url.rstrip("/") == candidate.api_url.rstrip("/")
                                and c.model == candidate.model and c.key_env == candidate.key_env
                                for c in candidates)
            if not already_there:
                candidates.append(candidate)
    return LLMRouter(candidates, max_tokens=MAX_TOKENS_PER_CALL, stop=["<end_code>"])


def start_mcp_server(task_file: Path) -> McpClientManager | None:
    """Start mcp_tools_mbpp.py for this task. If it fails, the agent works without tools."""
    try:
        return McpClientManager(
            stdio_cmd=[sys.executable, str(MCP_SERVER_FILE)],
            env={"MBPP_TASK_FILE": str(task_file.resolve())},   # the note: which task to test
        )
    except Exception as exc:
        print(f"Warning: MCP server not available, running without tools: {exc}", file=sys.stderr)
        return None


def solve(args: argparse.Namespace) -> SolutionOutput:
    """Load the task and the configs, build the agent and run it."""
    try:
        task = MBPPTaskInput.model_validate_json(args.task_file.read_text())
    except (OSError, ValidationError) as exc:
        return failed_output("unknown", f"Could not read task file: {exc}")

    try:
        sandbox_config = SandboxConfig.model_validate_json(args.sandbox_config.read_text())
    except (OSError, ValidationError) as exc:
        return failed_output(str(task.task_id), f"Could not read sandbox config: {exc}")

    try:
        llm = build_llm(args)
    except (OSError, ValidationError) as exc:
        return failed_output(str(task.task_id), f"Could not read models config: {exc}")
    except NoCandidateError as exc:
        return failed_output(str(task.task_id), f"Missing API key: {exc}")

    limits = AgentLimits(
        max_iterations=args.max_iterations,
        max_input_tokens=args.max_input_tokens,
        max_output_tokens=args.max_output_tokens,
        max_time_seconds=args.timeout,
    )

    mcp_client = None if args.no_tools else start_mcp_server(args.task_file)
    try:
        manual = tools_manual(tool_specs_from(mcp_client.tools)) if mcp_client else ""
        agent = Agent(llm=llm, system_prompt=build_system_prompt(manual), benchmark="mbpp",
                      limits=limits, sandbox_config=sandbox_config, mcp_client=mcp_client)
        return agent.run(task_id=str(task.task_id), task_prompt=build_task_prompt(task))
    finally:
        if mcp_client is not None:
            mcp_client.close()                # also stops the MCP server process


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