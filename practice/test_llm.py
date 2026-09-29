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
result = client.generate([{"role": "user", "content": "Say hello in one word."}])
print(result)