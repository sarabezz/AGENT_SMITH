"""The agent loop: Thought -> Code -> Observation, with per-step metrics and hard limits."""
import time
from dataclasses import dataclass

from core.extraction import extract_code
from core.llm import LLMClient
from core.models_public import SolutionOutput, StepMetrics
from core.sandbox import Sandbox

MAX_OBSERVATION_CHARS = 2_000
TEMPLATE_MARGIN_TOKENS = 20   # extra tokens added by the chat template on each request
NO_CODE_MESSAGE = (
    "No ```python code block was found in your response. "
    "Write your code inside a ```python block and end it with <end_code>."
)
NO_OUTPUT_MESSAGE = "(code executed successfully, no output)"


@dataclass
class AgentLimits:
    """Hard limits for one task. Defaults: MBPP limits from the moulinette README."""
    max_iterations: int = 10
    max_input_tokens: int = 4_000
    max_output_tokens: int = 1_000
    max_time_seconds: float = 60.0


def estimate_tokens(text: str) -> int:
    """Rough token count: about 4 characters per token."""
    return len(text) // 4 + 1


def build_observation(code: str | None, output: str) -> str:
    """Turn the sandbox result into the message the LLM will read."""
    if code is None:
        return "Observation: " + NO_CODE_MESSAGE
    if output == "":
        output = NO_OUTPUT_MESSAGE
    if len(output) > MAX_OBSERVATION_CHARS:
        output = (output[:MAX_OBSERVATION_CHARS]
                  + f"\n[output truncated: only the first {MAX_OBSERVATION_CHARS} characters are shown]")
    return "Observation: " + output


class Agent:
    """Runs the Thought -> Code -> Observation loop on one task."""

    def __init__(self, llm: LLMClient, system_prompt: str,
                 benchmark: str, limits: AgentLimits) -> None:
        self.llm = llm
        self.system_prompt = system_prompt
        self.benchmark = benchmark
        self.limits = limits

    def run(self, task_id: str, task_prompt: str) -> SolutionOutput:
        """Solve one task and always return a SolutionOutput (never crashes on LLM errors)."""
        start_time = time.perf_counter()
        sandbox = Sandbox()
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": task_prompt},
        ]
        steps: list[StepMetrics] = []
        total_input = 0
        total_output = 0
        total_requests = 0
        next_input_estimate = estimate_tokens(self.system_prompt + task_prompt) + TEMPLATE_MARGIN_TOKENS
        error: str | None = None

        for step in range(1, self.limits.max_iterations + 1):
            # 0. Can we afford another LLM call?
            error = self._check_budget(start_time, total_input, total_output, next_input_estimate)
            if error is not None:
                break

            # 1. THOUGHT + CODE: ask the LLM
            try:
                reply = self.llm.generate(messages)
            except Exception as exc:
                error = f"LLM request failed: {exc}"
                break
            total_requests += reply.retries + 1
            total_input += reply.input_tokens
            total_output += reply.output_tokens

            # 2. Extract the code and 3. OBSERVATION: run it
            code = extract_code(reply.text)
            output = sandbox.run(code) if code is not None else ""
            observation = build_observation(code, output)

            # 4. Record this step
            steps.append(StepMetrics(
                step=step,
                input_tokens=reply.input_tokens,
                output_tokens=reply.output_tokens,
                request_time_ms=reply.request_time_ms,
                api_url=self.llm.api_url,
                model_name=self.llm.model_name,
                llm_output=reply.text,
                sandbox_input=code or "",
                sandbox_output=observation,
                retries=reply.retries,
            ))

            # 5. Did the LLM call final_answer?
            if sandbox.is_done:
                break

            # 6. Add this turn to the conversation for the next iteration
            messages.append({"role": "assistant", "content": reply.text})
            messages.append({"role": "user", "content": observation})
            next_input_estimate = (reply.input_tokens + reply.output_tokens
                                   + estimate_tokens(observation) + TEMPLATE_MARGIN_TOKENS)

        if not sandbox.is_done and error is None:
            error = f"Reached {self.limits.max_iterations} iterations without final_answer"

        return SolutionOutput(
            task_id=task_id,
            benchmark=self.benchmark,
            success=sandbox.is_done,
            solution=str(sandbox.final_answer_value) if sandbox.is_done else "",
            iterations=len(steps),
            total_requests=total_requests,
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            total_time_seconds=time.perf_counter() - start_time,
            steps=steps,
            system_prompt=self.system_prompt,
            error=error,
        )

    def _check_budget(self, start_time: float, total_input: int,
                      total_output: int, next_input_estimate: int) -> str | None:
        """Return why we must stop before the next LLM call, or None if we can continue."""
        elapsed = time.perf_counter() - start_time
        if elapsed >= self.limits.max_time_seconds:
            return f"Time limit reached ({elapsed:.1f}s)"
        if total_input + next_input_estimate > self.limits.max_input_tokens:
            return "Stopped: the next request would exceed the input token limit"
        if total_output + self.llm.max_tokens > self.limits.max_output_tokens:
            return "Stopped: the next request could exceed the output token limit"
        return None