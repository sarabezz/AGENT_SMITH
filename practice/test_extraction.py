from core.extraction import extract_code

cases = {
    "cerrado": "Thought: ok\n```python\nprint(1)\n```",
    "sin codigo": "Thought: I think I am done.",
    "cortado": "Thought: ok\n```python\ndef f(x):\n    return x * 2\nprint(f(3))",
    "sin cerrar con end_code": "Thought: ok\n```python\nprint(2)\n<end_code>",
}

for name, text in cases.items():
    print(f"{name:25} → {extract_code(text)}")