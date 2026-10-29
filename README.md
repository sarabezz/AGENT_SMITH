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
benchmarked with six free models.

**Main features:**

- A **Thought → Code → Observation** loop, with loop detection, a step-budget warning and
  context compaction
- A **sandbox** in a separate process, with four layers of protection
- **MCP tools**, available in the sandbox as normal Python functions
- A **model router** with fallback, cooldowns and daily-limit detection
- **Benchmark scripts** that run the whole grid day after day and validate every solution

## System architecture

Agent Smith is made of **separate programs** that talk to each other:

```
┌──────────────────────── agent process ────────────────────────┐
│  agent_mbpp / agent_swebench   (command line, one task)        │
│        │                                                       │
│        ▼                                                       │
│  Agent loop (core/agent.py) ──────▶ LLM router ──────▶ OpenRouter / Groq
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
│ code, with the   │  │ mcp_tools_swebench.py ──▶ Docker container
│ security checks  │  │   (read_file, run_tests, ...)    │   (SWE-bench only)
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
| **Evaluation interface** | `sandbox.py` | `ExecutionSandbox`: `execute(code)` and `close()`, a thin wrapper around `core/sandbox.py` |
| | `models.py`, `core/models_public.py` | the data models: task inputs, sandbox configuration, solution output, step metrics |
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
| **Tests** | `practice/test_*.py`, `practice/attacks.py` | unit tests and sandbox escape attempts |

## Agent loop

The agent follows a **Thought → Code → Observation** loop (`core/agent.py`).

**Before the loop**, the model receives two messages:

1. **The system prompt**: the rules (one code block per turn, always `print` the tools' results,
   submit with `final_answer(...)`), a method to follow, and a **tools manual** generated
   automatically from the MCP server.
2. **The task**: the MBPP problem, or the SWE-bench issue as a real user wrote it on GitHub.
   The hidden tests are **never** shown to the model.

**Each step:**

| # | What happens |
|---|---|
| 0 | **Check the budget**: time, input tokens (estimated for the next request) and output tokens. If the next request would break a limit, stop. |
| 1 | **Ask the model**. It replies with a short *Thought* and one Python code block. |
| 2 | **Extract the code** from the reply (tolerant to small format mistakes). |
| 3 | **Run it in the sandbox**, and build the **Observation**: what the code printed, or its error. |
| 4 | **Add notes** when needed: the reply was cut, the code block was never closed, the model sent the same reply twice, or only 1–3 steps are left. |
| 5 | **Record the step metrics**: tokens, request time, model, the code and its output. |
| 6 | If the code called `final_answer(...)`, **stop**. Otherwise, add the reply and the Observation to the history, and go back to step 0. |

**Example of one SWE-bench turn:**

```
Thought: I look for the definition of the function mentioned in the issue.
print(search_code("def symbols", "sympy/core"))

Observation: sympy/core/symbol.py:586:def symbols(names, *, cls=Symbol, **args) -> Any:
```

**Lessons built into the loop** (each one fixes a real failure seen during development):

- **Incomplete replies are removed** from the history: a reply cut by the token limit is
  replaced by a short placeholder, because the model tends to imitate its own history and a
  broken reply would poison the next turns.
- **Loop detection**: if the model sends exactly the same reply twice, it is told so.
- **Step-budget warning**: in the last 3 steps, the model is reminded to submit, because some
  models fixed the bug but ran out of steps without calling `final_answer`.
- **Context compaction** (SWE-bench): the whole history is sent at every step, so older
  Observations are shortened to 400 characters and only the last 2 are kept in full. This keeps
  every request small (see the benchmark).
- **Auto-submit** (SWE-bench): if the model changed the code but never submitted, the real
  `git diff` of the container is submitted anyway, and the run is marked as not submitted by the
  model.

**At the end**, the agent writes a **solution JSON**: the solution, success, iterations, tokens,
time, every step's metrics, and the error if there was one. For SWE-bench, the solution is always
the **real** `git diff` of the container, never the text the model typed.

## Sandbox design

The model's code is never trusted. It runs behind **two lines of defense**: a separate
**process**, and **four protections** inside that process.

### Line 1: a separate worker process (`core/sandbox.py`, `core/sandbox_worker.py`)

The agent (the "boss") starts a fresh Python **worker process** and talks to it through a pipe.

- **Time limit.** The boss waits for the result with a deadline. If the code takes too long
  (an infinite loop, for example), the worker is killed and replaced, and the model is told
  that its variables were lost.
- **Crash recovery.** If the worker dies for any reason, the boss starts a new one and returns
  a clear message instead of crashing the agent.
- **The clock pauses during tool calls**: a slow tool (like running a test suite) is not
  counted against the model's time limit.
- **Variables persist** between steps, because the same worker is reused until the task ends.

### Line 2: four protections inside the worker (`core/sandbox_runtime.py`)

The model's code runs with its **own restricted copy** of Python's built-in functions, so the
dangerous ones can be removed without breaking our own code, which keeps the real ones.

| # | Protection | How |
|---|---|---|
| 1 | **Imports** | only modules from an allowlist (e.g. `math`, `collections.*`) can be imported; the error lists the allowed ones |
| 2 | **Blocked builtins** | `eval`, `exec`, `compile`, `input`, `exit`, `globals`, `getattr`, … are replaced by functions that raise a clear error |
| 3 | **Static check** | before running anything, the code is parsed (`ast`) and rejected if it touches an attribute starting with `_` (like `random._os`) or a name starting with `__` |
| 4 | **Files** | `open()` only works inside the allowed directories; the path is resolved first (`..` and symbolic links), and file descriptors are refused |

Every error becomes **text** for the model, never a crash of the agent. Even
`raise SystemExit` is caught: the worker keeps running, and the model keeps its variables.

**Defense in depth.** No single protection is enough. For example, if `random` is allowed, the
model could try to reach `os` through `random._os`: protection 3 refuses `._os`, and protection
2 blocks `getattr(random, "_" + "os")`, which would build the same name as a string.

### Submitting a function

In MBPP, the model submits a **function object**: `final_answer(count_vowels)`. The sandbox
turns it into **source code**: the imports, the latest version of the function, and every
helper function or constant it uses, taken from the code that already ran without errors.
Lines that call something (like `result = run_tests(f)`) are never copied, so the solution
works on its own anywhere.

### Configuration

`sandbox_template.json` sets the allowed imports, the allowed directories, the time limit and
the memory limit. Without a configuration, the strictest defaults are used.

## Tool implementation

Tools follow the **Model Context Protocol (MCP)**: each benchmark has its own **MCP server**,
and the agent connects to it as a **client**. The model never talks to the server directly: it
calls the tools as normal Python functions inside the sandbox.

### From an MCP tool to a Python function

```
model's code:  run_tests("sympy/core/tests/test_symbol.py")
  → bridge function (worker)  → pipe →  boss (core/sandbox.py)   ← the time limit pauses
  → MCP client (mcp_client.py) → stdio → MCP server → Docker container
  ← the result travels back as text, and the model's code continues
```

- **The servers** are written with **FastMCP**: each tool is a normal Python function, and its
  name, parameters and docstring become its description (`tools/list`).
- **Bridges** (`core/tool_bridge.py`): for every tool, a Python function with the **same
  signature** is created in the sandbox. It checks the arguments, turns a function argument into
  its source code, and sends the call to the boss.
- **The tools manual** in the system prompt is generated from the same descriptions, so the
  prompt always matches the real tools.
- **The MCP client** is synchronous for the rest of the code, but the MCP library is
  asynchronous: an **event loop runs in its own thread** for the whole task and keeps the
  connection open; each call is handed to it and waited for (300 s at most).
- **Errors become text.** A failing tool returns `Tool error: ...`, which the model reads in
  its Observation.

### MBPP tools (`mcp_tools_mbpp.py`)

| Tool | What it does |
|---|---|
| `run_tests(function)` | runs the task's own tests on the model's function, in a **separate, temporary sandbox**, and reports which ones failed and why |

Besides this tool, the MBPP server also exposes the other two MCP primitives, for any MCP client
that connects to it: the task as a **resource** (`mbpp://task`: description, signature and
tests), and a short solving method as a **prompt** (`solve_mbpp_task`). Our agent builds its own
prompt from the task file, so it does not need them.

### SWE-bench tools (`mcp_tools_swebench.py`)

| Tool | What it does |
|---|---|
| `search_code(pattern, path)` | `grep` over the `.py` files (50 matches at most) |
| `list_files(path)` | the contents of a folder (folders end with `/`) |
| `read_file(path, start_line, end_line)` | a file with line numbers, 300 lines at most per call |
| `edit_file(path, old_text, new_text)` | replaces a text that must appear **exactly once** |
| `run_command(command)` | runs a shell command (e.g. to reproduce the bug) |
| `run_tests(path)` | runs the project's own tests (`bin/test` for sympy, `pytest` otherwise) |
| `get_patch()` | the `git diff` of every change: the solution |

**Safety choices:**

- Every command runs **inside the task's Docker container** (`docker exec`), never on the host.
  `run_command` and `run_tests` refuse to run at all without a container.
- `safe_path` refuses any path that leaves the repository (`../../etc/passwd`), and every path
  or pattern is quoted with `shlex.quote`, so the shell can never interpret it as a command.
- New file content is sent through **stdin**, never inside the command line, so the shell can
  never change it or run parts of it.
- Long outputs are shortened to 6,000 characters, keeping the **start and the end**, where the
  errors and test summaries are.
- `core/container.py` starts the container with `with`, and **always** removes it at the end,
  even after an error.

## Benchmark results and analysis

The full report, with the setup, every table, the ablation, the limitations and the costs, is in
[`BENCHMARK_REPORT.md`](BENCHMARK_REPORT.md). The raw per-run numbers are generated by
`make_report.py` in [`benchmark/RESULTS.md`](benchmark/RESULTS.md).

**SWE-bench (3 real GitHub issues, free models only):**

| Model | Correct | Avg iterations | Avg time (s) | Cost per solved task (paid prices) |
|---|---|---|---|---|
| nemotron-3-super-120b | **3/3** | 24.7 | 75.3 | **$0.0094** |
| north-mini-code (cohere) | 2/3 | 24.3 | 131.2 | no paid version |
| qwen3.8-27b (Groq) | 2/3 | 16.3 | 384.2 | $0.0613 |
| dots-3-note-preview | 1/3 | 18.0 | 109.4 | no paid version |
| nemotron-3.5-lightning | 0/3 | 30.0 | 90.6 | — |
| *nemotron-3-ultra-550b (extra)* | *1/1* | *26.0* | *182.5* | *$0.0660* |

**8 of 15** runs of the grid were correct (53%), validated with the official grader.

**Ablation (MBPP, with vs. without the `run_tests` tool):** same accuracy (5/5), but **half the
iterations** (1.2 vs 2.4) and **half the tokens**: with the tool, the agent tests and submits in
the same step.

**Main findings:**

- **Submitted ≠ correct**: dots submitted 3/3 but solved 1/3, so every solution must be checked
  with the real tests.
- **Bigger ≠ better**: the 550B model's free endpoint kept timing out; the 120B model solved
  everything and was the fastest.
- **Small models explore without deciding**: lightning used all 30 steps and never edited the
  code.
- **Reading costs more than writing**: the whole history is resent at every step, so input tokens
  are about 87% of the cost; context compaction keeps every request small.
- **The best model was also the cheapest per solution**: under one cent per fix.

## Instructions

### Requirements

- **Python 3.10** and **[uv](https://docs.astral.sh/uv/)** (dependency manager)
- **Docker** (only for SWE-bench), running before you start a task
- A free API key from **[OpenRouter](https://openrouter.ai/)** and/or **[Groq](https://groq.com/)**

### Installation

```bash
git clone https://github.com/sarabezz/AGENT_SMITH.git
cd AGENT_SMITH
uv sync
```

Create a `.env` file at the root with your keys (it is in `.gitignore` and never committed):

```bash
OPENROUTER_API_KEY=your-key-here
GROQ_API_KEY=your-key-here
```

### Configuration

- **`models.json`**: the providers and the models to try, in order of preference. It contains
  only the **names** of the environment variables that hold the keys, never the keys.
- **`sandbox_template.json`**: the sandbox limits:

| Setting | Value |
|---|---|
| `authorized_imports` | `math`, `collections`, `itertools`, `re`, `json`, `typing`, `functools`, `operator`, `heapq`, `bisect`, `copy`, `string`, `random`, `datetime`, `array`, `cmath` |
| `allowed_directories` | `/testbed`, `/tmp/agent` |
| `max_execution_time_seconds` | 30 |
| `max_memory_mb` | 512 |

### Running one task

```bash
# MBPP
uv run python -m agent_mbpp --task-file benchmark/tasks/mbpp/2.json --output solution.json \
    --model-name nvidia/nemotron-3-super-120b-a12b:free \
    --provider-url https://openrouter.ai/api/v1 --api-key-env OPENROUTER_API_KEY

# SWE-bench (Docker must be running; the first run downloads the task's image, several GB)
uv run python -m agent_swebench --task-file benchmark/tasks/swebench/sympy__sympy-23534.json \
    --output solution.json \
    --model-name nvidia/nemotron-3-super-120b-a12b:free \
    --provider-url https://openrouter.ai/api/v1 --api-key-env OPENROUTER_API_KEY
```

- `--help` lists every option (limits, sandbox configuration, models configuration).
- `--no-fallback` uses **only** the given model; without it, the other models of `models.json`
  are used as backups.
- `--no-tools` (MBPP only) runs the agent without the MCP server.
- Without any API key, set `AGENT_MOCK_LLM=1` to use a fake model that only checks the pipeline.

### Interactive sandbox

```bash
uv run sandbox sandbox_template.json
uv run sandbox sandbox_template.json --mcp-stdio "python mcp_tools_swebench.py"
```

Type Python code; an empty line ends a multi-line block, and `exit` (or Ctrl+D) closes it. With
`--mcp-stdio`, the server's tools are available as normal functions.

### Benchmark

```bash
uv run python run_benchmark.py --benchmark swebench --dry-run    # show the plan only
uv run python run_benchmark.py --benchmark swebench               # run what is missing
uv run python run_benchmark.py --benchmark mbpp --no-tools        # the ablation
uv run python make_report.py --validate                           # validate + build the tables
```

Runs that are already finished are skipped, so the same command can be launched every day until
the grid is complete. `--validate` needs the 42 grader (`moulinette`) in the parent folder.

### Tests

```bash
uv run python practice/test_core.py       # each test file runs on its own
uv run python practice/attacks.py         # sandbox escape attempts: all must be blocked
```

## Key concepts

- **Code as action**: instead of choosing from a fixed list of actions, the model writes Python
  code, which can combine several tool calls, loops and checks in one step.
- **ReAct-style loop**: reasoning (*Thought*), acting (*Code*) and observing the result
  (*Observation*), repeated until the task is solved.
- **Defense in depth**: process isolation, an import allowlist, blocked builtins, a static check
  and a file allowlist, so that no single hole is enough to escape.
- **MCP**: a standard protocol between an AI application (client) and the services it uses
  (servers), with three primitives: tools, resources and prompts.
- **Sync / async bridge**: an asyncio event loop in its own thread lets synchronous code use an
  asynchronous library.
- **Context management**: the whole history is resent at every step, so it must be kept small.
- **Reliability with free APIs**: fallback between models, cooldowns, and a different reaction
  to temporary and daily rate limits.
- **Honest evaluation**: hidden tests, validation in a clean environment, and "finished" kept
  separate from "correct".

## Resources

**References**

- [Model Context Protocol](https://modelcontextprotocol.io/): specification and documentation
- [MCP Python SDK (FastMCP)](https://github.com/modelcontextprotocol/python-sdk)
- [SWE-bench](https://www.swebench.com/): Jimenez et al., *SWE-bench: Can Language Models Resolve
  Real-World GitHub Issues?* (2023), [arXiv:2310.06770](https://arxiv.org/abs/2310.06770)
- MBPP: Austin et al., *Program Synthesis with Large Language Models* (2021),
  [arXiv:2108.07732](https://arxiv.org/abs/2108.07732)
- ReAct: Yao et al., *ReAct: Synergizing Reasoning and Acting in Language Models* (2022),
  [arXiv:2210.03629](https://arxiv.org/abs/2210.03629)
- CodeAct: Wang et al., *Executable Code Actions Elicit Better LLM Agents* (2024),
  [arXiv:2402.01030](https://arxiv.org/abs/2402.01030)
- Python documentation: [`ast`](https://docs.python.org/3/library/ast.html),
  [`multiprocessing`](https://docs.python.org/3/library/multiprocessing.html),
  [`asyncio`](https://docs.python.org/3/library/asyncio.html)
- [OpenRouter](https://openrouter.ai/docs) and [Groq](https://console.groq.com/docs) API
  documentation, [Docker documentation](https://docs.docker.com/)

**How AI was used**

AI (Claude, by Anthropic) was used as a pair programmer throughout the project:

- **Code**: AI wrote most of the code, following the design decisions I made and the problems I
  found while testing.
- **Explanations**: AI explained the concepts I needed (asyncio, MCP, Docker, `ast`,
  multiprocessing) with examples, until I could explain them myself.
- **Documentation**: AI drafted this README and the benchmark report from my own explanations
  and answers.

My own work:

- **Running and debugging** everything in the real environment: the agents, the official exam
  scripts, the grader, and every benchmark run, day after day for two weeks.
- **Decisions**: free models only, which models to replace or add, the ablation, the fixes to
  apply, and the final clean-up of the repository.
- **Configuration and secrets**: the models configuration, the API keys and the `.env` file.
- **Review**: I went through the whole code base line by line, in twelve review sessions, until
  I could explain and defend every part. My questions during these reviews led to improvements
  (for example, catching `SystemExit` so the sandbox keeps the model's variables).
- **Benchmark analysis**: I wrote the findings in my own words first; AI only polished the
  wording.

## Project Info

| | |
|---|---|
| **Language** | Python 3.10 |
| **Main libraries** | MCP Python SDK, OpenAI client, pydantic |
| **Tools** | uv, Docker |
| **School** | 42 Madrid |
| **Status** | ✅ Completed |
