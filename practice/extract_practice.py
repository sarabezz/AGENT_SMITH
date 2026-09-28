import re

# El patrón: guarda lo que haya entre ```python y ```
CODE_BLOCK_PATTERN = re.compile(r"```python\n(.*?)```", re.DOTALL)


def extract_code(llm_output: str) -> str | None:
    """Devuelve el código de los bloques ```python ... ```, o None si no hay ninguno."""
    blocks = CODE_BLOCK_PATTERN.findall(llm_output)   # lista con TODOS los bloques encontrados
    if not blocks:
        return None
    return "\n".join(block.strip() for block in blocks)  # si hay varios, los junta


# --- Prueba 1: respuesta normal ---
respuesta_1 = """Thought: Necesito ordenar la lista y coger el último.
``````python
def mayor(lista):
    return sorted(lista)[-1]
print(mayor([1, 5, 3]))
`````"""

# --- Prueba 2: el LLM solo habla, sin código ---
respuesta_2 = "Thought: Creo que ya he terminado, la función es correcta."

# --- Prueba 3: dos bloques de código en la misma respuesta ---
respuesta_3 = """Thought: Primero defino la función.
````python
def doble(n):
    return n * 2
````
Y ahora la pruebo:
````python
print(doble(4))
```"""

for i, respuesta in enumerate([respuesta_1, respuesta_2, respuesta_3], start=1):
    print(f"===== Prueba {i} =====")
    print(repr(extract_code(respuesta)))
