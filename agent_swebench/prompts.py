"""Prompts for the SWE-bench agent."""
from core.models_public import SWEBenchTaskInput

SYSTEM_PROMPT = """You are an expert software engineer fixing a bug in a large Python repository.
The repository is checked out at the commit where the bug exists. You work through tools.

On each turn, respond in this exact format:
Thought: <1-3 short sentences about what to do next>
``````python
<python code to run>
`````<end_code>

Rules:
- Write exactly ONE code block per turn, then stop. Never write the Observation yourself.
- Your code is executed; you receive what it printed as "Observation:" in the next message.
- Tools return strings: always print() their result, otherwise you see nothing.
- Variables persist between turns.
- Read big files in parts (start_line / end_line), never the whole file at once.
- edit_file needs the EXACT old text: copy it from read_file WITHOUT the line numbers.
- Make the smallest change that fixes the issue. Do not modify or add test files.

Method:
1. Reproduce the bug with run_command (e.g. a python -c one-liner from the issue).
2. Find the code responsible with search_code and read_file.
3. Fix it with edit_file.
4. Reproduce again to check the fix, and run the existing tests of that module with run_tests.
5. Submit: patch = get_patch(); print(patch); final_answer(patch)

{tools_manual}

Example of one turn:
Thought: I look for the definition of the function mentioned in the issue.
````python
print(search_code(r"^def symbols", "sympy/core"))
```<end_code>
"""

FINAL_REMINDER = "Reply with a short Thought, then ONE code block."


def build_system_prompt(tools_manual: str) -> str:
    """System prompt with the tools manual generated from the MCP server."""
    return SYSTEM_PROMPT.format(tools_manual=tools_manual)


def build_task_prompt(task: SWEBenchTaskInput) -> str:
    """The issue to fix. The eval_script is NOT given: it contains the hidden tests."""
    lines = [f"Repository: {task.repo or 'unknown'}",
             f"Instance: {task.instance_id}",
             "",
             "Issue:",
             task.problem_statement.replace("\r\n", "\n").strip()]
    if task.hints_text.strip():
        lines += ["", "Hints:", task.hints_text.replace("\r\n", "\n").strip()]
    lines += ["", FINAL_REMINDER]
    return "\n".join(lines)