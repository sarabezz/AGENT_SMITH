"""A fake LLM for running the whole pipeline without any API key (AGENT_MOCK_LLM=1).

It does not think: it reads the function signature from the task and submits a placeholder
function. It is only meant to test the plumbing (agent loop, sandbox, MCP, metrics, JSON).
"""
import re
import time

from core.llm import LLMResponse, estimate_tokens

MOCK_ENV = "AGENT_MOCK_LLM"
MOCK_NAME = "mock"
SIGNATURE_PATTERN = re.compile(r"Signature:\s*(def\s+(\w+)\s*\(.*?\))\s*:")


class MockLLM:
    """Same interface as LLMClient / LLMRouter: generate(), max_tokens, api_url, model_name."""

    def __init__(self, max_tokens: int = 400) -> None:
        self.max_tokens = max_tokens
        self.api_url = MOCK_NAME
        self.model_name = MOCK_NAME

    def generate(self, messages: list[dict[str, str]],
                 max_tokens: int | None = None) -> LLMResponse:
        """Reply with a placeholder solution in the expected Thought + code format."""
        start = time.perf_counter()
        prompt = "\n".join(m["content"] for m in messages)
        match = SIGNATURE_PATTERN.search(prompt)
        if match:
            header, name = match.group(1), match.group(2)
            code = f"{header}:\n    return None\n\nfinal_answer({name})"
        else:
            code = 'final_answer("mock answer")'
        text = f"Thought: I am a mock model, I submit a placeholder.\n```python\n{code}\n```"
        return LLMResponse(
            text=text,
            input_tokens=estimate_tokens(prompt),
            output_tokens=estimate_tokens(text),
            request_time_ms=(time.perf_counter() - start) * 1000,
            retries=0,
            finish_reason="stop",
            usage_estimated=True,
        )