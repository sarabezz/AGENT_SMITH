import io
import traceback
from contextlib import redirect_stdout


class Sandbox:
    """Ejecuta código, recuerda variables y detecta cuándo el LLM ha terminado."""

    def __init__(self) -> None:
        self.namespace: dict = {}
        self.is_done: bool = False           # la bandera: ¿ha terminado?
        self.final_answer_value = None       # aquí guardaremos la solución
        # metemos el "timbre" en el cuaderno con el nombre que usará el LLM
        self.namespace["final_answer"] = self._final_answer

    def _final_answer(self, answer) -> None:
        """Lo que pasa cuando el código del LLM llama a final_answer(...)."""
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


# ---- Simulación: lo que el LLM "escribiría" en cada vuelta ----
fake_llm_code = [
    # Vuelta 1: primer intento, con el fallo
    "def mayor(lista):\n    return sorted(lista)[0]\nprint(mayor([1, 5, 3]))",
    # Vuelta 2: lo corrige
    "def mayor(lista):\n    return sorted(lista)[-1]\nprint(mayor([1, 5, 3]))",
    # Vuelta 3: ya funciona → entrega la solución
    'solucion = "def mayor(lista): return sorted(lista)[-1]"\nfinal_answer(solucion)',
    # Vuelta 4: esto NO debería llegar a ejecutarse
    'print("Si ves esto, algo va mal")',
]

sandbox = Sandbox()

for step, code in enumerate(fake_llm_code, start=1):
    print(f"===== Vuelta {step} =====")
    observation = sandbox.run(code)
    print("Observation:", observation)
    if sandbox.is_done:
        print("🔔 final_answer recibido:", sandbox.final_answer_value)
        break