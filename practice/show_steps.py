"""Print every step of a solution.json in full, to debug the agent."""
import json
import sys

with open(sys.argv[1]) as f:
    data = json.load(f)

for s in data["steps"]:
    print(f"\n===== Step {s['step']} | in={s['input_tokens']} out={s['output_tokens']} "
          f"retries={s['retries']} =====")
    print(s["llm_output"])
    print("----- sandbox output -----")
    print(s["sandbox_output"])

print("\nerror:", data["error"])