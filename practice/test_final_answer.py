from core.sandbox import Sandbox

sb = Sandbox()

# Vuelta 1: versión con un fallo
print(sb.run("import math\ndef area(r):\n    return r * r\nprint(area(1))"))

# Vuelta 2: la corrige y la prueba
print(sb.run("def area(r):\n    return math.pi * r * r\nassert round(area(1), 2) == 3.14\nprint('All tests passed')"))

# Vuelta 3: entrega LA FUNCIÓN, no un texto
print(sb.run("final_answer(area)"))

print("Done:", sb.is_done)
print("Solution:\n" + sb.final_answer_value)