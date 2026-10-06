"""Phase 8: which free OpenRouter models follow our format? (1 request per model, 50 free/day)."""
import os
import time

from dotenv import load_dotenv
from openai import OpenAI

OPENROUTER_URL = "https://openrouter.ai/api/v1"
QUESTION = [{"role": "user", "content": "Reply with one short Thought, then a ```python block "
                                       "that prints 2 + 3, then <end_code>."}]
CANDIDATES = [
    "cohere/north-mini-code:free",
    "poolside/laguna-s-2.1:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "google/gemma-4-31b-it:free",
    "thinkingmachines/inkling:free",
    "nvidia/nemotron-3.5-lightning:free",
]


def main() -> None:
    load_dotenv()
    client = OpenAI(base_url=OPENROUTER_URL, api_key=os.environ["OPENROUTER_API_KEY"],
                    max_retries=0, timeout=90)
    for model in CANDIDATES:
        print(f"===== {model}")
        start = time.perf_counter()
        try:
            response = client.chat.completions.create(
                model=model, messages=QUESTION, max_tokens=400,  # type: ignore[arg-type]
                stop=["<end_code>"], extra_body={"reasoning": {"enabled": False}})
        except Exception as exc:
            print(f"ERROR: {type(exc).__name__}: {str(exc)[:200]}\n")
            continue
        choice = response.choices[0]
        usage = response.usage
        print(f"finish_reason={choice.finish_reason!r} time={time.perf_counter() - start:.1f}s "
              f"in={usage.prompt_tokens if usage else '?'} out={usage.completion_tokens if usage else '?'}")
        print((choice.message.content or "(EMPTY)")[:300], "\n")


if __name__ == "__main__":
    main()