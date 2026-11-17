"""`bull stack install`: the static self-test, then the registry install."""

from __future__ import annotations

from pathlib import Path

from bull.Modules.stackflow.Contracts import StackInstaller
from bull.Modules.stacks.Contracts import Stack, StackError, StackRegistry
from bull.Modules.stacktest.Contracts import StackTester


def check_static(tester: StackTester, registry: StackRegistry, path: Path) -> None:
    """Refuse the stack folder at `path` unless its static self-test passes.

    Loads the folder with `registry.load_path` (its `StackError` propagates) and runs
    `tester.static`. Installs nothing.

    Raises:
        StackError: the folder can't be loaded, or the static check found problems
            (every problem is listed in the message).
    """
    stack = registry.load_path(path)
    report = tester.static(stack)
    if report.ok:
        return
    problems = "\n".join(f"- {problem}" for problem in report.problems)
    if not problems:
        problems = "- the static self-test did not pass"
    raise StackError(
        f"the stack at {path} fails its static self-test:\n{problems}",
        f"fix the problems, then run `bull stack test {path} --static` until it passes",
    )


class LiveStackInstaller(StackInstaller):
    """Installs a stack folder after its static self-test passes.

    Args:
        tester: runs the static self-test.
        registry: loads the folder and installs it.
    """

    def __init__(self, tester: StackTester, registry: StackRegistry) -> None:
        self._tester = tester
        self._registry = registry

    def install(self, path: Path) -> Stack:
        """`check_static`, then `registry.install`; nothing is installed on refusal."""
        check_static(self._tester, self._registry, path)
        return self._registry.install(path)
