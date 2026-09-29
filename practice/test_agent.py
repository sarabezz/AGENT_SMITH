import os

from dotenv import load_dotenv

from core.agent import Agent, AgentLimits
from core.llm import LLMClient
from practice.agent_practice import SYSTEM_PROMPT, TASK

load_dotenv()
llm = LLMClient(
    api_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
    model_name="qwen/qwen3.8-27b:free",
    max_tokens=300,
    stop=["<end_code>"],
    extra_body={"reasoning": {"enabled": False}},
)
agent = Agent(llm=llm, system_prompt=SYSTEM_PROMPT, benchmark="mbpp", limits=AgentLimits())
result = agent.run(task_id="test-palindrome", task_prompt=TASK)
print(result.model_dump_json(indent=2))