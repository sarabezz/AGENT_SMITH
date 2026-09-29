"""Client for OpenAI-compatible LLM APIs, with retries and per-call metrics."""
import time
from dataclasses import dataclass
from typing import Any

from openai import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    OpenAI,
    RateLimitError,
)

# Temporary errors worth retrying (rate limit, network, server hiccups)
RETRYABLE_ERRORS = (RateLimitError, APITimeoutError, APIConnectionError, InternalServerError)


@dataclass
class LLMResponse:
    """Result of one successful LLM call plus the metrics the evaluation requires."""
    text: str
    input_tokens: int
    output_tokens: int
    request_time_ms: float
    retries: int
    finish_reason: str          # "stop" = finished normally, "length" = cut by max_tokens

    @property
    def was_truncated(self) -> bool:
        """True if the reply was cut because it reached max_tokens."""
        return self.finish_reason == "length"


class LLMClient:
    """Talks to any OpenAI-compatible provider (OpenRouter, Groq, ...)."""

    def __init__(
        self,
        api_url: str,
        api_key: str,
        model_name: str,
        max_tokens: int = 400,
        stop: list[str] | None = None,
        extra_body: dict[str, Any] | None = None,
        max_retries: int = 3,
        wait_seconds: float = 5.0,
    ) -> None:
        self.api_url = api_url
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.stop = stop
        self.extra_body = extra_body
        self.max_retries = max_retries
        self.wait_seconds = wait_seconds
        self._client = OpenAI(base_url=api_url, api_key=api_key)

    def generate(self, messages: list[dict[str, str]],
                 max_tokens: int | None = None) -> LLMResponse:
        """Send the conversation and return the reply. Retries on temporary errors.

        max_tokens overrides the client default for this call only.
        """
        limit = max_tokens if max_tokens is not None else self.max_tokens
        retries = 0
        while True:
            start = time.perf_counter()          # the clock starts right before EACH attempt
            try:
                response = self._client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,           # type: ignore[arg-type]
                    max_tokens=limit,
                    stop=self.stop,
                    extra_body=self.extra_body,
                )
            except RETRYABLE_ERRORS:
                retries += 1
                if retries > self.max_retries:
                    raise                        # give up: let the agent loop handle it
                time.sleep(self.wait_seconds)
                continue                         # go back to the top of the while
            elapsed_ms = (time.perf_counter() - start) * 1000

            choice = response.choices[0]
            usage = response.usage
            return LLMResponse(
                text=choice.message.content or "",
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
                request_time_ms=elapsed_ms,
                retries=retries,
                finish_reason=choice.finish_reason or "",
            )