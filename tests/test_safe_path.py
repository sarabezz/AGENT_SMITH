import pytest

from mcp_tools_swebench import safe_path


@pytest.mark.parametrize("path, expected", [
    ("sympy/core/basic.py", "sympy/core/basic.py"),
    ("/testbed/sympy/core/basic.py", "sympy/core/basic.py"),
    ("./sympy//core/basic.py", "sympy/core/basic.py"),
    ("sympy/../setup.py", "setup.py"),
])
def test_valid_paths(path, expected):
    assert safe_path(path) == expected


@pytest.mark.parametrize("path", [
    "../etc/passwd",
    "sympy/../../etc",
    "/etc/passwd",
    "/testbed2/secret",
    "..",
])
def test_paths_outside_repo_are_refused(path):
    with pytest.raises(ValueError):
        safe_path(path)