import os
import time

from dotenv import load_dotenv
from openai import OpenAI, RateLimitError

load_dotenv()

api_key = os.getenv("OPENROUTER_API_KEY")
if api_key is None:
    raise SystemExit("Error: falta OPENROUTER_API_KEY en el archivo .env")

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=api_key,
)

MODEL = "qwen/qwen3.8-27b:free"
REASONING_ON = False   # <- lo cambiaremos a False en la segunda prueba
MAX_RETRIES = 3       # cuántas veces reintentamos como máximo
WAIT_SECONDS = 10     # cuánto esperamos entre intentos

messages = [
    {"role": "system", "content": "Eres un asistente que responde en una sola frase."},
    {"role": "user", "content": "¿Qué es un agente de IA?"},
]

response = None
retries = 0
start = time.time()
while response is None:
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            max_tokens=500,
            extra_body={"reasoning": {"enabled": REASONING_ON}},
        )
    except RateLimitError:
        retries += 1
        if retries > MAX_RETRIES:
            raise SystemExit(f"Error: sigue saturado tras {MAX_RETRIES} reintentos")
        print(f"429 (saturado). Reintento {retries}/{MAX_RETRIES} en {WAIT_SECONDS} s...")
        time.sleep(WAIT_SECONDS)
elapsed_ms = (time.time() - start) * 1000

message = response.choices[0].message
print("Respuesta:", message.content)
print("Pensamiento oculto:", getattr(message, "reasoning", None))
if response.usage is not None:
    print("Tokens de entrada:", response.usage.prompt_tokens)
    print("Tokens de salida:", response.usage.completion_tokens)
print("Reintentos:", retries)
print(f"Tiempo: {elapsed_ms:.0f} ms")