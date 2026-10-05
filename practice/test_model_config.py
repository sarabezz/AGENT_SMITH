"""Phase 7.3: show the fallback list built from models.json and the keys in .env."""
from dotenv import load_dotenv

from core.model_config import build_candidates, load_models_config


def main() -> None:
    load_dotenv()
    config = load_models_config()
    candidates = build_candidates(config)
    print(f"{len(config.models)} models in models.json -> {len(candidates)} candidates with a key:")
    for number, c in enumerate(candidates, 1):
        print(f"  {number}. {c.provider:<10} {c.model:<26} key={c.key_env:<20} extra_body={c.extra_body}")


if __name__ == "__main__":
    main()