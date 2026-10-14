"""Smoke test: does each candidate model answer right now, with a code block?"""
import os

import dotenv
import openai

dotenv.load_dotenv()
client = openai.OpenAI(base_url="https://openrouter.ai/api/v1",
                       api_key=os.environ["OPENROUTER_API_KEY"], max_retries=0, timeout=60)

CANDIDATES = [
    "nvidia/nemotron-3.5-lightning:free",
    "thinkingmachines/inkling:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "dots-studio/dots-3-note-preview:free",
]

for model in CANDIDATES:
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content":
                       "Write a Python function add(a, b) in a ```python block. Be brief."}],
            max_tokens=400,
            extra_body={"reasoning": {"enabled": False}},
        )
        choice = response.choices[0]
        content = choice.message.content or ""
        has_code = "```" in content
        print(f"OK   {model}: finish={choice.finish_reason} code_block={has_code}")
        print("     ", content[:100].replace("\n", " | ") or "(EMPTY)")
    except openai.APIStatusError as exc:
        print(f"FAIL {model}: {exc.status_code} {str(exc)[:120]}")