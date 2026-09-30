"""Harmless 'attacks' to check what the sandbox allows. Run it after each protection."""
from pathlib import Path

from core.models_public import SandboxConfig
from core.sandbox import Sandbox

CONFIG = SandboxConfig.model_validate_json(Path("sandbox_template.json").read_text())
CONFIG = CONFIG.model_copy(update={"max_execution_time_seconds": 5})   # shorter, only for tests

# Imports that would be FORBIDDEN normally: used to check that the network layer still holds
PERMISSIVE = CONFIG.model_copy(update={"authorized_imports": ["*"]})

ATTACKS = {
    "1. import os (list my files)":
        (CONFIG, 'import os\nprint(os.listdir("."))'),
    "2. read my .env (only the first 15 chars)":
        (CONFIG, 'print(open(".env").read()[:15])'),
    "3. internet access":
        (CONFIG, 'import urllib.request\nprint(urllib.request.urlopen("https://example.com").status)'),
    "4. run a terminal command":
        (CONFIG, 'import subprocess\nsubprocess.run(["echo", "I can run commands on your computer"])'),
    "5. dangerous builtin eval":
        (CONFIG, 'print(eval("2 + 2"))'),
    "6. dangerous builtin exec":
        (CONFIG, 'exec("print(\'exec works\')")'),
    "7. getattr to reach hidden things":
        (CONFIG, 'print(getattr(print, "__name__"))'),
    "8. BACK DOOR: os hidden inside random":
        (CONFIG, 'import random\nprint(random._os.listdir("."))'),
    "9. BACK DOOR: climb to every class with dunders":
        (CONFIG, 'print(len(().__class__.__base__.__subclasses__()), "classes reachable")'),
    "10. PATH TRICK: escape with '..'":
        (CONFIG, 'print(open("/tmp/agent/../../etc/hostname").read())'),
    "11. PATH TRICK: similar folder name":
        (CONFIG, 'print(open("/tmp/agent_evil/secret.txt").read())'),
    "12. INFINITE LOOP (should stop after 5 s)":
        (CONFIG, 'while True:\n    pass'),
    "13. MEMORY BOMB (should hit the 512 MB limit)":
        (CONFIG, 'data = []\nwhile True:\n    data.append(" " * 10_000_000)'),
    "14. NETWORK LAYER 2 (every import allowed, network must still fail)":
        (PERMISSIVE, 'import urllib.request\nprint(urllib.request.urlopen("https://example.com").status)'),
    "15. SystemExit (the worker dies, the agent must survive)":
        (CONFIG, 'raise SystemExit'),
    "16. [SHOULD WORK] allowed import math":
        (CONFIG, 'import math\nprint(math.sqrt(16))'),
    "17. [SHOULD WORK] normal builtins":
        (CONFIG, 'print(len([1, 2, 3]), sorted([3, 1, 2]), max(4, 9))'),
    "18. [SHOULD WORK] a normal class with __init__":
        (CONFIG, 'class Point:\n    def __init__(self, x):\n        self.x = x\nprint(Point(3).x)'),
    "19. [SHOULD WORK] read a file in /tmp/agent":
        (CONFIG, 'print(open("/tmp/agent/test.txt").read())'),
}


def main() -> None:
    for name, (config, code) in ATTACKS.items():
        sandbox = Sandbox(config)
        output = sandbox.run(code).strip()
        sandbox.close()
        last_line = output.splitlines()[-1] if output else "(no output)"
        print(f"{name}\n   → {last_line}\n")


if __name__ == "__main__":
    main()