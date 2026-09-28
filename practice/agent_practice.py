import io
import os
import re
import time
import traceback
from contextlib import redirect_stdout

from dotenv import load_dotenv
from openai import OpenAI, RateLimitError

# ================= Configuración =================
MODEL = "qwen/qwen3.8-27b:free"
MAX_ITERATIONS = 10      # límite de vueltas de MBPP
MAX_RETRIES = 3
WAIT_SECONDS = 10

SYSTEM_PROMPT = """You are an expert Python programmer solving coding tasks step by step.

On each turn, respond in this exact format:
Thought: <your reasoning about what to do next>
````````python
<python code to run>
```````<end_code>

Rules:
- Write exactly ONE code block per turn, then stop. Never write the Observation yourself.
- Your code is executed; you will receive its output as "Observation:" in the next message.
- Use print() to see values, otherwise you will see nothing.
- Variables and functions persist between turns.
- When your function passes the tests, call final_answer(solution) where solution is a string with the full function code.

Example:
Task: Write a function max_num(lst) that returns the largest number.
Tests:
assert max_num([1, 5, 3]) == 5

Thought: I will sort the list, take the last element, and run the test.
``````python
def max_num(lst):
    return sorted(lst)[-1]

assert max_num([1, 5, 3]) == 5
print("All tests passed")
`````<end_code>
Observation: All tests passed

Thought: The tests pass. I will submit the function code.
````python
solution = '''def max_num(lst):
    return sorted(lst)[-1]'''
final_answer(solution)
```<end_code>
"""

TASK = """Task: Write a function is_palindrome(s) that returns True if the string s reads the same forwards and backwards, and False otherwise.
Tests:
assert is_palindrome("radar") == True
assert is_palindrome("hola") == False
assert is_palindrome("") == True"""


# ================= Pieza 1: la sandbox (fase 2) =================
class Sandbox:
    def __init__(self) -> None:
        self.namespace: dict = {}
        self.is_done: bool = False
        self.final_answer_value = None
        self.namespace["final_answer"] = self._final_answer

    def _final_answer(self, answer) -> None:
        self.final_answer_value = answer
        self.is_done = True

    def run(self, code: str) -> str:
        buffer = io.StringIO()
        try:
            with redirect_stdout(buffer):
                exec(code, self.namespace)
        except Exception:
            buffer.write(traceback.format_exc())
        return buffer.getvalue()


# ================= Pieza 2: extracción de código (paso 3.1) =================
CODE_BLOCK_PATTERN = re.compile(r"```python\n(.*?)```", re.DOTALL)


def extract_code(llm_output: str) -> str | None:
    blocks = CODE_BLOCK_PATTERN.findall(llm_output)
    if not blocks:
        return None
    return "\n".join(block.strip() for block in blocks)


# ================= Pieza 3: llamar al LLM con reintentos (fase 1) =================
def call_llm(client: OpenAI, messages: list):
    retries = 0
    while True:
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                max_tokens=500,
                stop=["<end_code>"],                              # <- NUEVO: le cortamos aquí
                extra_body={"reasoning": {"enabled": False}},     # sin pensamiento oculto
            )
            return response, retries
        except RateLimitError:
            retries += 1
            if retries > MAX_RETRIES:
                raise SystemExit(f"Error: sigue saturado tras {MAX_RETRIES} reintentos")
            print(f"429 (saturado). Reintento {retries}/{MAX_RETRIES} en {WAIT_SECONDS} s...")
            time.sleep(WAIT_SECONDS)


# ================= Pieza 4: EL BUCLE DEL AGENTE (nuevo) =================
def run_agent() -> None:
    load_dotenv()
    api_key = os.getenv("OPENROUTER_API_KEY")
    if api_key is None:
        raise SystemExit("Error: falta OPENROUTER_API_KEY en el archivo .env")
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)

    sandbox = Sandbox()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": TASK},
    ]
    total_input = 0
    total_output = 0

    for step in range(1, MAX_ITERATIONS + 1):
        print(f"\n========== Vuelta {step} ==========")

        # 1. THOUGHT + CODE: el LLM piensa y escribe
        response, retries = call_llm(client, messages)
        llm_output = response.choices[0].message.content or ""
        if response.usage is not None:
            total_input += response.usage.prompt_tokens
            total_output += response.usage.completion_tokens
        print("LLM:\n" + llm_output)

        # 2. Sacar el código de su respuesta
        code = extract_code(llm_output)

        # 3. OBSERVATION: ejecutarlo (o avisar si no hay código)
        if code is None:
            observation = ("Observation: No ```python code block found in your response. "
                           "Write your code inside a ```python block.")
        else:
            output = sandbox.run(code)
            if output == "":
                output = "(code executed successfully, no output)"
            observation = "Observation: " + output
        print("\n" + observation)

        # 4. ¿Ha tocado el timbre?
        if sandbox.is_done:
            print("\n🔔 final_answer:\n" + str(sandbox.final_answer_value))
            break

        # 5. Añadir esta vuelta a la conversación para la siguiente
        messages.append({"role": "assistant", "content": llm_output})
        messages.append({"role": "user", "content": observation})

    if not sandbox.is_done:
        print(f"\n⚠️ Se acabaron las {MAX_ITERATIONS} vueltas sin final_answer")
    print(f"\nTokens totales → entrada: {total_input}, salida: {total_output}")


if __name__ == "__main__":
    run_agent()
