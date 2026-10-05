"""Extract executable Python code from raw LLM responses."""
import re
from dataclasses import dataclass

# Opening fence: ```python, ```py, ```python3, ```Python... or a bare ``` (any case, spaces allowed)
_OPEN_FENCE = r"```[ \t]*(?:python3|python|py)?[ \t]*\n"
CODE_BLOCK_PATTERN = re.compile(_OPEN_FENCE + r"(.*?)```", re.DOTALL | re.IGNORECASE)
UNCLOSED_BLOCK_PATTERN = re.compile(_OPEN_FENCE + r"(.*)\Z", re.DOTALL | re.IGNORECASE)
END_CODE_MARKER = "<end_code>"


@dataclass
class ExtractedCode:
    """Code found in an LLM response."""
    code: str
    malformed: bool     # True if the code block was never closed


def extract_code(llm_output: str) -> ExtractedCode | None:
    """Return the code of the Python blocks, or None if there is none.

    0. Windows line endings (\\r\\n) are normalized first.
    1. Closed blocks: all of them are joined together.
    2. Otherwise, an unclosed block (e.g. the reply was cut): everything after the
       opening fence is taken, and the result is marked as malformed.
    Blocks of other languages (```json, ```bash...) are ignored.
    """
    text = llm_output.replace("\r\n", "\n")
    blocks = CODE_BLOCK_PATTERN.findall(text)
    if blocks:
        return ExtractedCode(code="\n".join(block.strip() for block in blocks), malformed=False)

    match = UNCLOSED_BLOCK_PATTERN.search(text)
    if match:
        code = match.group(1).replace(END_CODE_MARKER, "").strip()
        return ExtractedCode(code=code, malformed=True)

    return None