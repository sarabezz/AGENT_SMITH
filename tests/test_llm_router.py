import httpx
import pytest
from openai import APIStatusError

from core.llm_router import is_daily_limit


def make_error(cls, status, message):
    """Build a real openai error, like the API raises, without calling any API."""
    request = httpx.Request("POST", "https://example.com")
    response = httpx.Response(status, request=request)
    return cls(message, response=response, body=None)


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