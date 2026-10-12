"""final_answer(f) must also carry the helper functions f uses."""
from core.sandbox_runtime import SandboxRuntime

runtime = SandboxRuntime()
print(runtime.run("def is_even(n):\n    return n % 2 == 0\n"))
print(runtime.run("def unused():\n    return 42\n"))
print(runtime.run("def count_even(xs):\n    return sum(1 for x in xs if is_even(x))\n"))
print(runtime.run("final_answer(count_even)"))

print("--- submitted solution ---")
print(runtime.final_answer_value)

namespace = {}
exec(runtime.final_answer_value, namespace)          # run the solution ALONE, like the moulinette
print("works alone:", namespace["count_even"]([1, 2, 3, 4]))