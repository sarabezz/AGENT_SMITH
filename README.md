*This project has been created as part of the 42 curriculum by saraberm.*

# Agent Smith

An AI agent that solves programming tasks by writing and running Python code in a secure
sandbox, using tools through the Model Context Protocol (MCP).

## Description

A language model on its own can only write text. Agent Smith connects it with the real world:
the model writes Python code, the agent runs it in a secure sandbox, and the model reads the
result to decide its next step, until it submits a solution.

The agent is evaluated on two benchmarks:

- **MBPP**: short Python problems. The model writes a function and checks it with the task's
  tests.
- **SWE-bench**: real bugs from real GitHub projects (sympy, xarray). The model works inside a
  Docker container with the buggy repository: it searches the code, reproduces the bug, edits
  the files, runs the tests and submits its fix as a git patch.

The goal is an agent that is **reliable** and **safe**: every action is limited (time, tokens,
memory, imports, files), every solution is checked with the real tests, and the same agent was
benchmarked with six free models (five in the grid + ultra).

**Main features:**

- A **Thought → Code → Observation** loop, with loop detection, a step-budget warning and
  context compaction
- A **sandbox** in a separate process, with four layers of protection
- **MCP tools**, available in the sandbox as normal Python functions
- A **model router** with fallback, cooldowns and daily-limit detection
- **Benchmark scripts** that run the whole grid day after day and validate every solution


## System architecture

Agent Smith is made of **four separate programs** that talk to each other:

```
┌──────────────────────── agent process ────────────────────────┐
│  agent_mbpp / agent_swebench   (command line, one task)        │
│        │                                                       │
│        ▼                                                       │
│  Agent loop (core/agent.py) ──────▶ LLM router ──────▶ 🌍 OpenRouter / Groq
│        │                            (core/llm_router.py)       │
│        ▼                                                       │
│  Sandbox "boss" (core/sandbox.py)                              │
│        │   ▲                                                   │
│        │   └── MCP client (mcp_client.py) ◀── its own thread   │
└────────┼──────────────┼────────────────────────────────────────┘
    pipe │              │ stdio
         ▼              ▼
┌─ worker process ─┐  ┌─ MCP server process ─────────────┐
│ runs the model's │  │ mcp_tools_mbpp.py                │
│ code, with the   │  │ mcp_tools_swebench.py ──▶ 📦 Docker container
│ security checks  │  │   (read_file, run_tests, ...)    │    (SWE-bench only)
└──────────────────┘  └──────────────────────────────────┘
```

- **The agent process** runs the loop, talks to the model, and coordinates everything.
- **The worker process** runs the model's code. Keeping it in a separate process means a crash,
  an infinite loop or a memory explosion never takes the agent down: the worker is simply
  replaced.
- **The MCP server process** owns the tools. For SWE-bench, every command it runs happens inside
  a disposable **Docker container** that holds the buggy repository.

### Main files

| Group | File | Role |
|---|---|---|
| **Entry points** | `agent_mbpp/`, `agent_swebench/` | command-line agents: one task in, one solution JSON out |
| | `core/sandbox_cli.py` | an interactive sandbox, to try code and tools by hand |
| **Agent** | `core/agent.py` | the Thought → Code → Observation loop, limits and metrics |
| | `core/extraction.py` | extracts the code block from the model's reply |
| **Models** | `core/llm.py` | one OpenAI-compatible client, with retries and token counts |
| | `core/llm_router.py` | fallback between models, cooldowns, daily-limit detection |
| | `core/model_config.py`, `models.json` | which providers and models to use (key **names** only, never keys) |
| | `core/llm_setup.py`, `core/mock_llm.py` | builds the model list; a fake model for tests |
| **Sandbox** | `core/sandbox.py` | the boss: time limit, crash recovery, tool calls |
| | `core/sandbox_worker.py`, `core/sandbox_runtime.py` | the worker process and its four protections |
| **Tools** | `mcp_client.py` | synchronous client for one MCP server |
| | `core/tool_bridge.py` | turns each MCP tool into a normal Python function in the sandbox |
| | `mcp_tools_mbpp.py`, `mcp_tools_swebench.py` | the two MCP servers |
| | `core/container.py` | starts and always removes the SWE-bench Docker container |
| **Benchmark** | `run_benchmark.py`, `make_report.py` | runs the model × task grid; validates and builds the tables |
