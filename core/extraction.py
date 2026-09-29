"""Extract executable Python code from raw LLM responses."""
import re
from dataclasses import dataclass

CODE_BLOCK_PATTERN = re.compile(r"```python\n(.*?)```", re.DOTALL)
UNCLOSED_BLOCK_PATTERN = re.compile(r"```python\n(.*)\Z", re.DOTALL)
END_CODE_MARKER = "<end_code>"


@dataclass
class ExtractedCode:
    """Code found in an LLM response."""
    code: str
    malformed: bool     # True if the ```python block was never closed


def extract_code(llm_output: str) -> ExtractedCode | None:
    """Return the code of the ```python blocks, or None if there is none.

    1. Closed blocks: all of them are joined together.
    2. Otherwise, an unclosed block (e.g. the reply was cut): everything after
```python is taken, and the result is marked as malformed.
    """
    blocks = CODE_BLOCK_PATTERN.findall(llm_output)
    if blocks:
        return ExtractedCode(code="\n".join(block.strip() for block in blocks), malformed=False)

    match = UNCLOSED_BLOCK_PATTERN.search(llm_output)
    if match:
        code = match.group(1).replace(END_CODE_MARKER, "").strip()
        return ExtractedCode(code=code, malformed=True)

    return None
