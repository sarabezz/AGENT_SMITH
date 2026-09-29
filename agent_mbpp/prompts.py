"""Prompts for the MBPP agent."""
from core.models_public import MBPPTaskInput

SYSTEM_PROMPT = """You are an expert Python programmer solving coding tasks step by step.

On each turn, respond in this exact format:
Thought: <1-3 short sentences about what to do next>
`````````python
<python code to run>
````````<end_code>

Rules:
- Write exactly ONE code block per turn, then stop. Never write the Observation yourself.
- Keep your Thought short. Do not explain the examples, just write the code.
- Write code without comments, to keep your reply short.
- Your code is executed; you will receive its output as "Observation:" in the next message.
- Use print() to see values, otherwise you will see nothing.
- Variables and functions persist between turns.
- The function must have exactly the given signature.
- When the tests pass, submit by calling final_answer with your function, e.g. final_answer(max_num).

Example:
Task: Write a function that returns the largest number of a list.
Signature: def max_num(lst):
Tests:
assert max_num([1, 5, 3]) == 5

Thought: Sort the list and take the last element, then run the test.
```````python
def max_num(lst):
    return sorted(lst)[-1]

assert max_num([1, 5, 3]) == 5
print("All tests passed")
``````<end_code>
Observation: All tests passed

Thought: The tests pass, I submit the function.
`````python
final_answer(max_num)
````<end_code>
"""

FINAL_REMINDER = "Reply with a one-sentence Thought, then the code block."


def build_task_prompt(task: MBPPTaskInput) -> str:
    """Turn the moulinette task into the user message, in the same format as the example."""
    lines = [
        f"Task: {task.task_definition}",
        f"Signature: {task.function_definition}",
    ]
    if task.test_imports:
        lines.append("Test imports:")
        lines.extend(task.test_imports)
    lines.append("Tests:")
    lines.extend(task.test_list)
    lines.append("")
    lines.append(FINAL_REMINDER)
    return "\n".join(lines)