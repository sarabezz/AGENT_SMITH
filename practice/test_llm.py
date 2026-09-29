import os

from dotenv import load_dotenv

from core.llm import LLMClient

load_dotenv()
client = LLMClient(
    api_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
    model_name="qwen/qwen3.8-27b:free",
    extra_body={"reasoning": {"enabled": False}},
)

short = client.generate([{"role": "user", "content": "Say hello in one word."}])
print("Normal:", repr(short.text), "| finish_reason:", short.finish_reason,
      "| truncated:", short.was_truncated)

cut = client.generate([{"role": "user", "content": "Count from 1 to 50, separated by commas."}],
                      max_tokens=5)
print("Cortada:", repr(cut.text), "| finish_reason:", cut.finish_reason,
      "| truncated:", cut.was_truncated)