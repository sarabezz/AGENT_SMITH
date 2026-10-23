"""A Docker container for one SWE-bench task: start it, use it, ALWAYS remove it."""
import subprocess
import sys

PULL_TIMEOUT = 1800         # seconds: SWE-bench images are several GB
COMMAND_TIMEOUT = 120


class ContainerError(Exception):
    """Docker is not available, or the image / container could not be prepared."""


def _docker(*args: str, timeout: float = COMMAND_TIMEOUT) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise ContainerError("the docker command was not found (is Docker Desktop running?)") from None
    except subprocess.TimeoutExpired:
        raise ContainerError(f"docker {args[0]} took more than {timeout} s") from None


class TaskContainer:
    """Use it with `with`: the container is removed at the end, even after an error.

    The container is named after the task 
    (e.g. sympy__sympy-23534): the exam cleans up
    containers by that name, and only one container per task can exist at a time.
    """

    def __init__(self, image: str, name: str) -> None:
        self.image = image
        self.name = name

    def __enter__(self) -> "TaskContainer":
        if not self.image:
            raise ContainerError("the task has no docker image")
        if _docker("image", "inspect", self.image).returncode != 0:
            print(f"[docker] pulling {self.image} (first time only, can take minutes)", file=sys.stderr)
            pulled = _docker("pull", self.image, timeout=PULL_TIMEOUT)
            if pulled.returncode != 0:
                raise ContainerError(f"cannot pull {self.image}: {pulled.stderr.strip()[-300:]}")
        _docker("rm", "-f", self.name)                       # leftover from a crashed run
        started = _docker("run", "-d", "--name", self.name, self.image, "sleep", "infinity")
        if started.returncode != 0:
            raise ContainerError(f"cannot start the container: {started.stderr.strip()[-300:]}")
        return self

    def __exit__(self, *exc_info: object) -> None:
        _docker("rm", "-f", self.name)