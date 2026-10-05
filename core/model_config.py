"""Models configuration (models.json): which providers and models to use, in order of preference."""
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, model_validator

DEFAULT_MODELS_CONFIG = Path(__file__).resolve().parent.parent / "models.json"


class ProviderConfig(BaseModel):
    """One provider: where it is and which environment variables may hold its API keys."""
    api_url: str
    api_key_envs: list[str]


class ModelEntry(BaseModel):
    """One model of the fallback list, served by one of the providers."""
    provider: str
    model: str
    extra_body: dict[str, Any] = {}     # provider-specific options (e.g. turn reasoning off)


class ModelsConfig(BaseModel):
    """The whole models.json file."""
    providers: dict[str, ProviderConfig]
    models: list[ModelEntry]

    @model_validator(mode="after")
    def _providers_exist(self) -> "ModelsConfig":
        """Every model must use a provider declared in `providers`."""
        for entry in self.models:
            if entry.provider not in self.providers:
                raise ValueError(f"model '{entry.model}' uses unknown provider '{entry.provider}'")
        return self


@dataclass
class Candidate:
    """One concrete way to call an LLM: provider + model + ONE API key."""
    provider: str
    model: str
    api_url: str
    api_key: str
    key_env: str                        # name of the variable the key came from (for logs, never the key)
    extra_body: dict[str, Any]


def load_models_config(path: Path = DEFAULT_MODELS_CONFIG) -> ModelsConfig:
    """Read and validate models.json."""
    return ModelsConfig.model_validate_json(path.read_text())


def build_candidates(config: ModelsConfig,
                     env: Mapping[str, str] = os.environ) -> list[Candidate]:
    """Expand the config into the ordered list of candidates.

    Order = fallback order: model 1 with key 1, model 1 with key 2, ..., then model 2, ...
    Keys whose environment variable is missing or empty are skipped.
    """
    candidates = []
    for entry in config.models:
        provider = config.providers[entry.provider]
        for key_env in provider.api_key_envs:
            api_key = env.get(key_env, "")
            if api_key:
                candidates.append(Candidate(entry.provider, entry.model, provider.api_url,
                                            api_key, key_env, entry.extra_body))
    return candidates