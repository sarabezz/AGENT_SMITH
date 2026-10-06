"""Build the LLM used by an agent CLI: command-line model first, then the models.json fallbacks."""
import argparse
import os

from core.llm_router import LLMRouter
from core.mock_llm import MOCK_ENV, MOCK_NAME, MockLLM
from core.model_config import Candidate, ModelsConfig, build_candidates, load_models_config


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


def build_llm(args: argparse.Namespace, max_tokens: int) -> LLMRouter | MockLLM:
    """The command-line model first, then (unless --no-fallback) the models.json list.

    With AGENT_MOCK_LLM=1 (or --provider-url mock) a fake LLM is used: no API key needed.
    Raises NoCandidateError if no API key is available at all.
    """
    if is_mock(args):
        return MockLLM(max_tokens=max_tokens)
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
    return LLMRouter(candidates, max_tokens=max_tokens, stop=["<end_code>"])


def is_mock(args: argparse.Namespace) -> bool:
    """True when the fake LLM must be used (no API keys during the evaluation)."""
    return os.getenv(MOCK_ENV) == "1" or args.provider_url == MOCK_NAME