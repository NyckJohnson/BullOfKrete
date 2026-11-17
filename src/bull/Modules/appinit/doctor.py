"""`bull doctor`: the install and toolchain check."""

from __future__ import annotations

from bull.Modules.appinit.Contracts import Doctor, DoctorReport
from bull.Modules.claude_code.Contracts import Provider
from bull.Modules.foundation.Contracts import Runner
from bull.Modules.stacks.Contracts import CheckItem, Requirement, StackRegistry

_MIN_PYTHON = (3, 11)
_PYTHON_FIX = "install Python 3.11 or newer: https://www.python.org/downloads/"
_CORE_TOOLS = (
    Requirement("uv", "install uv: https://docs.astral.sh/uv/"),
    Requirement("git", "install git: https://git-scm.com/downloads"),
)


class LiveDoctor(Doctor):
    """Checks python, uv, git and the provider's tool; lists each stack's required tools.

    `python_version` is the running interpreter's (major, minor, micro).
    """

    def __init__(
        self,
        *,
        runner: Runner,
        registry: StackRegistry,
        provider: Provider,
        python_version: tuple[int, int, int],
    ) -> None:
        self._runner = runner
        self._registry = registry
        self._provider = provider
        self._python_version = python_version

    def run(self) -> DoctorReport:
        items = (
            self._python_item(),
            *(self._tool_item(requirement) for requirement in _CORE_TOOLS),
            self._provider.tool_check(),
        )
        stacks = tuple(
            (
                stack.manifest.name,
                tuple(self._tool_item(r) for r in stack.manifest.requires),
            )
            for stack in self._registry.all(False)
        )
        return DoctorReport(items=items, stacks=stacks)

    def _python_item(self) -> CheckItem:
        version = ".".join(str(part) for part in self._python_version)
        if self._python_version[:2] >= _MIN_PYTHON:
            return CheckItem(True, f"python {version}", "")
        return CheckItem(False, f"python {version} is older than 3.11", _PYTHON_FIX)

    def _tool_item(self, requirement: Requirement) -> CheckItem:
        if self._runner.which(requirement.tool) is not None:
            return CheckItem(True, f"{requirement.tool} found", "")
        return CheckItem(False, f"{requirement.tool} not found", requirement.hint)
