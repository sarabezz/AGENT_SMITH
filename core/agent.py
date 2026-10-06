"""The agent loop: Thought -> Code -> Observation, with per-step metrics and hard limits."""
import sys
import time
from dataclasses import dataclass
from typing import Any

from core.extraction import ExtractedCode, extract_code
from core.llm import LLMClient, LLMResponse, estimate_tokens
from core.models_public import SandboxConfig, SolutionOutput, StepMetrics
from core.sandbox import Sandbox

MAX_OBSERVATION_CHARS = 2_000
TEMPLATE_MARGIN_TOKENS = 20   # extra tokens added by the chat template on each request
MIN_OUTPUT_TOKENS = 30        # below this, a reply is too short to be useful
NO_CODE_MESSAGE = (
    "No ```python code block was found in your response. "
    "Write your code inside a ```python block and end it with <end_code>."
)
NO_OUTPUT_MESSAGE = "(code executed successfully, no output)"
UNCLOSED_BLOCK_NOTE = (
    "Your reply ended before the ```python block was closed, so it was removed from the "
    "conversation; the partial code was executed anyway, up to the end of your reply. "
    "Write the COMPLETE code again and close the block with ``` followed by <end_code>."
)
INCOMPLETE_PLACEHOLDER = "[My previous reply was incomplete and was removed.]"
OLD_OBSERVATION_CHARS = 400   # older observations are shortened to this size (if compaction is on)
SHORTENED_NOTE = "\n[older observation shortened to save tokens; call the tool again if you need it]"


@dataclass
class AgentLimits:
    """Hard limits for one task. Defaults: MBPP limits checked by the moulinette."""
    max_iterations: int = 10
    max_input_tokens: int = 6_000
    max_output_tokens: int = 1_500
    max_time_seconds: float = 120.0
    max_observation_chars: int = MAX_OBSERVATION_CHARS   # longer for SWE-bench (files, test logs)
    keep_full_observations: int | None = None   # None = never shorten; N = keep the last N complete


def is_incomplete(reply: LLMResponse, extracted: ExtractedCode | None) -> bool:
    """A reply is incomplete if we cut it (max_tokens) or if its code block was never closed."""
    return reply.was_truncated or (extracted is not None and extracted.malformed)


def build_observation(extracted: ExtractedCode | None, output: str,
                      reply: LLMResponse, max_tokens: int,
                      max_chars: int = MAX_OBSERVATION_CHARS) -> str:
    """Turn what happened into the message the LLM will read. It must never have to guess."""
    notes: list[str] = []
    if reply.was_truncated:
        notes.append(f"Your previous reply was cut off because it reached the limit of {max_tokens} "
                     "tokens, so it was removed from the conversation. Reply again with a "
                     "one-sentence Thought and short code without comments.")

    if extracted is None:
        if not reply.was_truncated:
            notes.append(NO_CODE_MESSAGE)
        return "Observation: No code was executed. " + " ".join(notes)

    if extracted.malformed and not reply.was_truncated:
        notes.append(UNCLOSED_BLOCK_NOTE)
    if output == "":
        output = NO_OUTPUT_MESSAGE
    if len(output) > max_chars:
        output = (output[:max_chars]
                  + f"\n[output truncated: only the first {max_chars} characters are shown]")

    observation = "Observation: " + output
    if notes:
        observation += "\nNote: " + " ".join(notes)
    return observation


def compact_history(messages: list[dict[str, str]], keep_full: int) -> None:
    """Shorten every observation except the last `keep_full` ones (in place).

    The task, the system prompt and the model's own code are never touched.
    """
    observation_indexes = [i for i, m in enumerate(messages)
                           if m["role"] == "user" and m["content"].startswith("Observation:")]
    for i in observation_indexes[:max(len(observation_indexes) - keep_full, 0)]:
        content = messages[i]["content"]
        if len(content) > OLD_OBSERVATION_CHARS and not content.endswith(SHORTENED_NOTE):
            messages[i] = {"role": "user", "content": content[:OLD_OBSERVATION_CHARS] + SHORTENED_NOTE}


def log_step(step: int, reply: LLMResponse, extracted: ExtractedCode | None) -> None:
    """One line per step on stderr (saved as stderr.log by the exam) to debug the agent."""
    malformed = extracted.malformed if extracted is not None else None
    print(f"[step {step}] in={reply.input_tokens} out={reply.output_tokens} "
          f"finish_reason={reply.finish_reason!r} retries={reply.retries} "
          f"code_found={extracted is not None} unclosed_block={malformed}", file=sys.stderr)


class Agent:
    """Runs the Thought -> Code -> Observation loop on one task."""

    def __init__(self, llm: LLMClient, system_prompt: str, benchmark: str,
                 limits: AgentLimits, sandbox_config: SandboxConfig,
                 mcp_client: Any = None) -> None:
        self.llm = llm
        self.system_prompt = system_prompt
        self.benchmark = benchmark
        self.limits = limits
        self.sandbox_config = sandbox_config
        self.mcp_client = mcp_client        # optional: its tools become functions in the sandbox

    def run(self, task_id: str, task_prompt: str) -> SolutionOutput:
        """Solve one task in a fresh sandbox, which is ALWAYS closed at the end."""
        sandbox = Sandbox(self.sandbox_config, mcp_client=self.mcp_client)
        try:
            return self._solve(task_id, task_prompt, sandbox)
        finally:
            sandbox.close()

    def _solve(self, task_id: str, task_prompt: str, sandbox: Sandbox) -> SolutionOutput:
        """The loop itself. Always returns a SolutionOutput (never crashes on LLM errors)."""
        start_time = time.perf_counter()
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
            # 0. Can we afford another LLM call? How many output tokens are left?
            error = self._check_budget(start_time, total_input, total_output, next_input_estimate)
            if error is not None:
                break
            max_tokens = min(self.llm.max_tokens, self.limits.max_output_tokens - total_output)

            # 1. THOUGHT + CODE: ask the LLM
            try:
                reply = self.llm.generate(messages, max_tokens=max_tokens)
            except Exception as exc:
                error = f"LLM request failed: {exc}"
                break
            total_requests += reply.retries + 1
            total_input += reply.input_tokens
            total_output += reply.output_tokens

            # 2. Extract the code and 3. OBSERVATION: run it in the sandbox
            extracted = extract_code(reply.text)
            output = sandbox.run(extracted.code) if extracted is not None else ""
            observation = build_observation(extracted, output, reply, max_tokens,
                                            self.limits.max_observation_chars)
            log_step(step, reply, extracted)

            # 4. Record this step (the FULL reply is always logged, even if incomplete)
            steps.append(StepMetrics(
                step=step,
                input_tokens=reply.input_tokens,
                output_tokens=reply.output_tokens,
                request_time_ms=reply.request_time_ms,
                api_url=self.llm.api_url,
                model_name=self.llm.model_name,
                llm_output=reply.text,
                sandbox_input=extracted.code if extracted is not None else "",
                sandbox_output=output,
                retries=reply.retries,
            ))

            # 5. Did the LLM call final_answer?
            if sandbox.is_done:
                break

            # 6. Add this turn to the conversation. An INCOMPLETE reply (cut by us, or with an
            #    unclosed code block) is replaced by a short placeholder, so the LLM cannot
            #    imitate it and we do not pay to resend it.
            if is_incomplete(reply, extracted):
                assistant_content = INCOMPLETE_PLACEHOLDER
                assistant_tokens = estimate_tokens(INCOMPLETE_PLACEHOLDER)
            else:
                assistant_content = reply.text
                assistant_tokens = reply.output_tokens
            messages.append({"role": "assistant", "content": assistant_content})
            messages.append({"role": "user", "content": observation})
            if self.limits.keep_full_observations is not None:
                compact_history(messages, self.limits.keep_full_observations)
            next_input_estimate = (reply.input_tokens + assistant_tokens
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
        if self.limits.max_output_tokens - total_output < MIN_OUTPUT_TOKENS:
            return "Stopped: the output token budget is exhausted"
        return None