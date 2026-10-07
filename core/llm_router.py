"""Several LLM candidates behind one generate(): if one fails, switch to the next one."""
import sys
import time
from dataclasses import dataclass, field
from typing import Any

from openai import APIStatusError, AuthenticationError, NotFoundError, PermissionDeniedError

from core.llm import RETRYABLE_ERRORS, LLMClient, LLMResponse
from core.model_config import Candidate

# Errors that will never go away for this candidate (bad key, model not found, no access)
PERMANENT_ERRORS = (AuthenticationError, PermissionDeniedError, NotFoundError)
COOLDOWN_SECONDS = 20.0     # a rate-limited candidate is skipped for this long
# Words that mean a 429 is a DAILY quota (OpenRouter "free-models-per-day", Groq "requests per
# day (RPD)"): waiting a few seconds will not help, so the candidate is disabled like a 401
DAILY_LIMIT_MARKERS = ("per-day", "per day", "daily")
MAX_ROUNDS = 3              # how many times we go through the whole list before giving up


class NoCandidateError(Exception):
    """Raised when there is no usable LLM at all (no keys, or every candidate failed)."""


@dataclass
class _Slot:
    """A candidate plus its client and its health."""
    candidate: Candidate
    client: LLMClient
    cooldown_until: float = 0.0          # perf_counter time until which we skip it
    disabled: bool = False               # permanent error: never use it again
    label: str = field(init=False)

    def __post_init__(self) -> None:
        self.label = f"{self.candidate.provider}/{self.candidate.model} ({self.candidate.key_env})"


def is_daily_limit(exc: Exception) -> bool:
    """True if the error is a 429 caused by a per-day quota (it only resets the next day)."""
    if getattr(exc, "status_code", None) != 429:
        return False
    text = str(exc).lower()
    return any(marker in text for marker in DAILY_LIMIT_MARKERS)


def _log(message: str) -> None:
    """Debug line on stderr (saved as stderr.log by the exam)."""
    print(f"[llm] {message}", file=sys.stderr)


class LLMRouter:
    """Same interface as LLMClient (generate, max_tokens, api_url, model_name), but with fallback.

    Order of preference = order of the candidates. A candidate that fails with a temporary
    error is skipped for COOLDOWN_SECONDS; one with a permanent error is never used again.
    api_url and model_name always describe the candidate that produced the LAST reply.
    """

    def __init__(self, candidates: list[Candidate], max_tokens: int = 400,
                 stop: list[str] | None = None, request_timeout: float = 60.0) -> None:
        if not candidates:
            raise NoCandidateError("no LLM available: no API key found for any configured model")
        self.max_tokens = max_tokens
        self._slots = [
            _Slot(c, LLMClient(api_url=c.api_url, api_key=c.api_key, model_name=c.model,
                               max_tokens=max_tokens, stop=stop, extra_body=c.extra_body or None,
                               max_retries=0, request_timeout=request_timeout))
            for c in candidates
        ]
        self.api_url = candidates[0].api_url
        self.model_name = candidates[0].model

    def generate(self, messages: list[dict[str, str]],
                 max_tokens: int | None = None) -> LLMResponse:
        """Ask the first healthy candidate; on failure switch to the next one without waiting."""
        failed_requests = 0
        last_error: Exception | None = None
        for round_number in range(1, MAX_ROUNDS + 1):
            for slot in self._slots:
                if slot.disabled or slot.cooldown_until > time.perf_counter():
                    continue
                try:
                    reply = slot.client.generate(messages, max_tokens=max_tokens)
                except PERMANENT_ERRORS as exc:
                    slot.disabled = True
                    failed_requests += 1
                    last_error = exc
                    _log(f"{slot.label} disabled ({type(exc).__name__}): {exc}")
                    continue
                except RETRYABLE_ERRORS + (APIStatusError,) as exc:
                    failed_requests += 1
                    last_error = exc
                    if is_daily_limit(exc):             # quota for today is used up
                        slot.disabled = True
                        _log(f"{slot.label} disabled (daily quota used up)")
                        continue
                    # temporary (429, timeout, 5xx) or provider-specific (e.g. 400 for an unknown
                    # extra_body option, 402 for a paid model): skip it for a while
                    slot.cooldown_until = time.perf_counter() + COOLDOWN_SECONDS
                    _log(f"{slot.label} failed ({type(exc).__name__}), trying the next one")
                    continue
                self.api_url = slot.candidate.api_url
                self.model_name = slot.candidate.model
                reply.retries += failed_requests        # every failed request counts as a retry
                return reply
            if round_number == MAX_ROUNDS or not self._wait_for_next_candidate():
                break
        raise NoCandidateError(f"every LLM candidate failed; last error: {last_error}")

    def _wait_for_next_candidate(self) -> bool:
        """Sleep until the first cooled-down candidate is available again. False if none is left."""
        active = [s for s in self._slots if not s.disabled]
        if not active:
            return False
        wait = min(s.cooldown_until for s in active) - time.perf_counter()
        if wait > 0:
            _log(f"all candidates are cooling down, waiting {wait:.0f} s")
            time.sleep(wait)
        return True