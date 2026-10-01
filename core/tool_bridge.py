"""Bridge functions: MCP tools exposed inside the sandbox as normal Python functions.

Inside the sandbox, `run_tests(code)` looks like any other function, but its body
only sends {"name", "args"} out of the sandbox and waits for the text answer.
The real tool runs in the MCP server, never inside the sandbox.
"""
import inspect
import json
import keyword
import re
from collections.abc import Callable
from typing import Any

ToolCaller = Callable[[str, dict[str, Any]], str]    # (tool name, arguments) -> text result
ValueConverter = Callable[[Any], Any]                 # applied to each argument before sending

JSON_TO_PYTHON_TYPES = {
    "string": "str", "integer": "int", "number": "float",
    "boolean": "bool", "array": "list", "object": "dict",
}


def tool_specs_from(tools: list[Any]) -> list[dict[str, Any]]:
    """Turn the MCP tools/list answer into plain dicts that can travel through the pipe."""
    specs = []
    for tool in tools:
        schema = tool.inputSchema or {}
        properties = schema.get("properties", {})
        required = list(schema.get("required", []))
        specs.append({
            "name": tool.name,
            "description": tool.description or "",
            "required": required,
            "optional": [p for p in properties if p not in required],
            "types": {p: JSON_TO_PYTHON_TYPES.get(info.get("type", ""), "Any")
                      for p, info in properties.items()},
        })
    return specs


def python_name(tool_name: str) -> str:
    """A valid Python identifier for a tool name (e.g. 'get-patch' -> 'get_patch')."""
    name = re.sub(r"\W", "_", tool_name)
    if not name or name[0].isdigit() or keyword.iskeyword(name):
        name = f"tool_{name}"
    return name


def _build_signature(spec: dict[str, Any]) -> inspect.Signature | None:
    """Signature like `run_tests(code)`: required parameters first, then optional ones."""
    try:
        params = [inspect.Parameter(p, inspect.Parameter.POSITIONAL_OR_KEYWORD)
                  for p in spec["required"]]
        params += [inspect.Parameter(p, inspect.Parameter.POSITIONAL_OR_KEYWORD, default=None)
                   for p in spec["optional"]]
        return inspect.Signature(params)
    except ValueError:              # a parameter name that is not valid in Python
        return None


def make_bridge(spec: dict[str, Any], call_tool: ToolCaller,
                convert: ValueConverter | None = None) -> Callable[..., str]:
    """Build the bridge function for one tool."""
    tool_name = spec["name"]
    signature = _build_signature(spec)

    def bridge(*args: Any, **kwargs: Any) -> str:
        # 1. Turn the Python call into {parameter: value}, with normal Python errors
        if signature is None:
            if args:
                raise TypeError(f"{tool_name}() only accepts keyword arguments")
            arguments = kwargs
        else:
            try:
                arguments = dict(signature.bind(*args, **kwargs).arguments)
            except TypeError as exc:
                raise TypeError(f"{tool_name}{signature}: {exc}") from None
        # 2. Optional conversion (e.g. a function -> its source code)
        if convert is not None:
            arguments = {key: convert(value) for key, value in arguments.items()}
        # 3. MCP sends JSON: refuse values that cannot be converted
        try:
            json.dumps(arguments)
        except (TypeError, ValueError):
            raise TypeError(f"{tool_name}(): arguments must be JSON values "
                            "(str, int, float, bool, None, list, dict)") from None
        # 4. Send the request out of the sandbox and wait for the text answer
        return call_tool(tool_name, arguments)

    bridge.__name__ = python_name(tool_name)
    bridge.__doc__ = spec["description"]
    return bridge


def tools_manual(tool_specs: list[dict[str, Any]]) -> str:
    """The tools section of the system prompt, generated from tools/list (empty if no tools)."""
    if not tool_specs:
        return ""
    lines = ["You can call these tools as normal Python functions. Each one returns a string.",
             "You can pass a function you defined as an argument: its source code is sent.", ""]
    for spec in tool_specs:
        params = [f"{p}: {spec['types'].get(p, 'Any')}" for p in spec["required"]]
        params += [f"{p}: {spec['types'].get(p, 'Any')} = None" for p in spec["optional"]]
        lines.append(f"- {python_name(spec['name'])}({', '.join(params)}) -> str")
        for line in inspect.cleandoc(spec["description"]).splitlines():
            lines.append(f"    {line}".rstrip())
    return "\n".join(lines)