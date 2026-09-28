"""Extract executable Python code from raw LLM responses."""
import re

CODE_BLOCK_PATTERN = re.compile(r"```python\n(.*?)```", re.DOTALL)


def extract_code(llm_output: str) -> str | None:
    """Return the code of every ```python block joined together, or None if there is none."""
    blocks = CODE_BLOCK_PATTERN.findall(llm_output)
    if not blocks:
        return None
    return "\n".join(block.strip() for block in blocks)