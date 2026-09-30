"""Harmless 'attacks' to check what the sandbox allows. Run it after each protection."""
from pathlib import Path

from core.models_public import SandboxConfig
from core.sandbox import Sandbox

CONFIG = SandboxConfig.model_validate_json(Path("sandbox_template.json").read_text())

ATTACKS = {
    "1. import os (list my files)":
        'import os\nprint(os.listdir("."))',
    "2. read my .env (only the first 15 chars)":
        'print(open(".env").read()[:15])',
    "3. internet access":
        'import urllib.request\nprint(urllib.request.urlopen("https://example.com").status)',
    "4. run a terminal command":
        'import subprocess\nsubprocess.run(["echo", "I can run commands on your computer"])',
    "5. dangerous builtin eval":
        'print(eval("2 + 2"))',
    "6. dangerous builtin exec":
        'exec("print(\'exec works\')")',
    "7. getattr to reach hidden things":
        'print(getattr(print, "__name__"))',
    "8. BACK DOOR: os hidden inside random":
        'import random\nprint(random._os.listdir("."))',
    "9. BACK DOOR: climb to every class with dunders":
        'print(len(().__class__.__base__.__subclasses__()), "classes reachable")',
    "10. [SHOULD WORK] allowed import math":
        'import math\nprint(math.sqrt(16))',
    "11. [SHOULD WORK] normal builtins":
        'print(len([1, 2, 3]), sorted([3, 1, 2]), max(4, 9))',
    "12. [SHOULD WORK] a normal class with __init__":
        'class Point:\n    def __init__(self, x):\n        self.x = x\nprint(Point(3).x)',
}

for name, code in ATTACKS.items():
    sandbox = Sandbox(CONFIG)
    output = sandbox.run(code).strip()
    last_line = output.splitlines()[-1] if output else "(no output)"
    print(f"{name}\n   → {last_line}\n")