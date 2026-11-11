from core.sandbox import Sandbox


def test_final_answer_works():
    sb = Sandbox()
    sb.run("def add(a, b):\n    return a + b")
    sb.run("final_answer(add)")
    assert sb.is_done
    assert "def add" in sb.final_answer_value


def test_latest_definition_wins():
    sb = Sandbox()
    sb.run("def add(a, b):\n    return a - b")
    sb.run("def add(a, b):\n    return a + b")
    sb.run("final_answer(add)")
    assert "a + b" in sb.final_answer_value
    assert "a - b" not in sb.final_answer_value


def test_helpers_are_included():
    sb = Sandbox()
    sb.run("def helper(x):\n    return x * 2")
    sb.run("def double_sum(a, b):\n    return helper(a) + helper(b)")
    sb.run("final_answer(double_sum)")
    assert "def helper" in sb.final_answer_value
    assert "def double_sum" in sb.final_answer_value


def test_calls_are_not_included():
    sb = Sandbox()
    sb.run("def add(a, b):\n    return a + b\nprint(add(1, 2))")
    sb.run("final_answer(add)")
    assert "def add" in sb.final_answer_value
    assert "print(add" not in sb.final_answer_value


def test_failed_block_is_not_saved():
    sb = Sandbox()
    sb.run("def add(a, b):\n    return a + b\nundefined_name")
    sb.run("final_answer(add)")
    assert not sb.is_done