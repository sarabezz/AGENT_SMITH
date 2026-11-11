from core.sandbox_runtime import SandboxRuntime


def test_normal_code_works():
    rt = SandboxRuntime()
    output = rt.run("print(1 + 1)")
    assert "2" in output


def test_import_is_blocked():
    rt = SandboxRuntime()
    output = rt.run("import os\nprint(os.getcwd())")
    assert "blocked" in output


def test_open_outside_is_blocked():
    rt = SandboxRuntime()
    output = rt.run('print(open("/etc/passwd").read())')
    assert "root:" not in output


def test_dunder_attribute_is_blocked():
    rt = SandboxRuntime()
    output = rt.run("print(().__class__)")
    assert "<class 'tuple'>" not in output


def test_exit_does_not_kill_sandbox():
    rt = SandboxRuntime()
    rt.run("raise SystemExit(1)")
    output = rt.run("print('still alive')")
    assert "still alive" in output