from core.extraction import extract_code
from core.sandbox import Sandbox

llm_output = 'Thought: test\n```python\nprint(2 + 3)\nfinal_answer("ok")\n```'

sb = Sandbox()
code = extract_code(llm_output)
print("Code:", repr(code))
print("Output:", repr(sb.run(code)))
print("Done:", sb.is_done, "| Answer:", sb.final_answer_value)