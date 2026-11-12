import copy

from core.agent import OLD_OBSERVATION_CHARS, SHORTENED_NOTE, compact_history


def make_history(n_observations, length=1000):
    """A fake conversation: system prompt, task, then (model code, observation) pairs."""
    messages = [
        {"role": "system", "content": "You are an agent."},
        {"role": "user", "content": "Task: fix the bug."},
    ]
    for i in range(n_observations):
        messages.append({"role": "assistant", "content": f"Thought {i}\nprint({i})"})
        messages.append({"role": "user", "content": "Observation: " + "x" * length})
    return messages


def observations(messages):
    return [m["content"] for m in messages if m["content"].startswith("Observation:")]


def test_old_observations_are_shortened():
    messages = make_history(4)
    compact_history(messages, keep_full=2)
    obs = observations(messages)
    assert obs[0].endswith(SHORTENED_NOTE)
    assert obs[1].endswith(SHORTENED_NOTE)
    assert len(obs[0]) == OLD_OBSERVATION_CHARS + len(SHORTENED_NOTE)


def test_last_observations_stay_full():
    messages = make_history(4)
    compact_history(messages, keep_full=2)
    obs = observations(messages)
    assert obs[2] == "Observation: " + "x" * 1000
    assert obs[3] == "Observation: " + "x" * 1000


def test_other_messages_are_never_touched():
    messages = make_history(4)
    before = copy.deepcopy(messages)
    compact_history(messages, keep_full=2)
    for old, new in zip(before, messages):
        if not old["content"].startswith("Observation:"):
            assert old == new


def test_short_observations_are_not_changed():
    messages = make_history(4, length=50)
    before = copy.deepcopy(messages)
    compact_history(messages, keep_full=2)
    assert messages == before


def test_shortening_twice_changes_nothing():
    messages = make_history(4)
    compact_history(messages, keep_full=2)
    once = copy.deepcopy(messages)
    compact_history(messages, keep_full=2)
    assert messages == once


def test_keep_full_bigger_than_observations():
    messages = make_history(4)
    before = copy.deepcopy(messages)
    compact_history(messages, keep_full=5)
    assert messages == before