import time
from types import SimpleNamespace

import httpx
import pytest
from openai import APIStatusError, NotFoundError

from core.llm_router import LLMRouter, NoCandidateError, is_daily_limit

MESSAGES = [{"role": "user", "content": "hi"}]


def make_error(cls, status, message):
    """Build a real openai error, like the API raises, without calling any API."""
    request = httpx.Request("POST", "https://example.com")
    response = httpx.Response(status, request=request)
    return cls(message, response=response, body=None)


# ---------- Part A: is_daily_limit ----------

@pytest.mark.parametrize("status, message, expected", [
    (429, "Rate limit exceeded: free-models-per-day", True),
    (429, "Rate limit reached for requests per day (RPD)", True),
    (429, "Rate limit exceeded, retry in 5 seconds", False),
    (500, "Internal error per day", False),
])
def test_is_daily_limit(status, message, expected):
    error = make_error(APIStatusError, status, message)
    assert is_daily_limit(error) == expected


def test_error_without_status_code_is_not_daily_limit():
    assert is_daily_limit(ValueError("per day")) is False


# ---------- Part B: generate, with fake models ----------

class FakeClient:
    """A fake model: raises the error we choose, or answers."""

    def __init__(self, error=None):
        self.error = error
        self.calls = 0

    def generate(self, messages, max_tokens=None):
        self.calls += 1
        if self.error:
            raise self.error
        return SimpleNamespace(content="hello", retries=0)


def make_router(*clients):
    """A router whose models are our fake clients (model0, model1, ...)."""
    candidates = [
        SimpleNamespace(provider="test", model=f"model{i}", key_env="FAKE_KEY",
                        api_url="https://example.com", api_key="fake", extra_body=None)
        for i in range(len(clients))
    ]
    router = LLMRouter(candidates)
    for slot, client in zip(router._slots, clients):
        slot.client = client
    return router


def test_first_model_answers():
    first, second = FakeClient(), FakeClient()
    router = make_router(first, second)
    router.generate(MESSAGES)
    assert router.model_name == "model0"
    assert second.calls == 0


def test_not_found_disables_the_model():
    first = FakeClient(make_error(NotFoundError, 404, "model not found"))
    second = FakeClient()
    router = make_router(first, second)
    reply = router.generate(MESSAGES)
    assert router._slots[0].disabled
    assert router.model_name == "model1"
    assert reply.retries == 1


def test_daily_limit_disables_the_model():
    first = FakeClient(make_error(APIStatusError, 429, "free-models-per-day"))
    router = make_router(first, FakeClient())
    router.generate(MESSAGES)
    assert router._slots[0].disabled


def test_temporary_429_only_pauses_the_model():
    first = FakeClient(make_error(APIStatusError, 429, "retry in 5 seconds"))
    router = make_router(first, FakeClient())
    router.generate(MESSAGES)
    assert not router._slots[0].disabled
    assert router._slots[0].cooldown_until > time.perf_counter()


def test_every_model_dead_raises():
    first = FakeClient(make_error(NotFoundError, 404, "model not found"))
    second = FakeClient(make_error(NotFoundError, 404, "model not found"))
    router = make_router(first, second)
    with pytest.raises(NoCandidateError):
        router.generate(MESSAGES)