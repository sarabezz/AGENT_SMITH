"""Phase 7.3: check which Groq models work with our agent settings (stop + reasoning off)."""
import os

from dotenv import load_dotenv
from openai import OpenAI

GROQ_URL = "https://api.groq.com/openai/v1"
QUESTION = [{"role": "user", "content": "Reply with one short Thought, then a ```python block "
                                       "that prints 2 + 3, then <end_code>."}]
CANDIDATES = [
    ("qwen/qwen3.8-27b", {"reasoning_effort": "none"}),
    ("qwen/qwen3.8-27b", {}),
    ("openai/gpt-oss-20b", {"reasoning_effort": "low"}),
    ("openai/gpt-oss-120b", {"reasoning_effort": "low"}),
]


def main() -> None:
    load_dotenv()
    client = OpenAI(base_url=GROQ_URL, api_key=os.environ["GROQ_API_KEY"], max_retries=0, timeout=60)
    for model, extra_body in CANDIDATES:
        print(f"===== {model}  extra_body={extra_body}")
        try:
            response = client.chat.completions.create(
                model=model, messages=QUESTION, max_tokens=400,  # type: ignore[arg-type]
                stop=["<end_code>"], extra_body=extra_body)
        except Exception as exc:
            print(f"ERROR: {type(exc).__name__}: {exc}\n")
            continue
        choice = response.choices[0]
        usage = response.usage
        print(f"finish_reason={choice.finish_reason!r} "
              f"in={usage.prompt_tokens if usage else '?'} out={usage.completion_tokens if usage else '?'}")
        print((choice.message.content or "")[:400], "\n")


if __name__ == "__main__":
    main()