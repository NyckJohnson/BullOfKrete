"""The `claude` launch command line and the tool check."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Sequence

from bull.Modules.foundation.Contracts import AppLayout
from bull.Modules.stacks.Contracts import CheckItem

INSTALL_FIX = "install Claude Code: https://docs.claude.com/claude-code"
_TOOL = "claude"
_VERSION_TIMEOUT = 30.0


def launch_argv(app: AppLayout, extra: Sequence[str]) -> list[str]:
    """`claude --plugin-dir <app>/.bull/plugin` followed by `extra` in order."""
    return [_TOOL, "--plugin-dir", str(app.plugin_dir), *(str(a) for a in extra)]


def tool_check() -> CheckItem:
    """Look `claude` up on PATH now; ok with its `--version` output, else the install fix."""
    found = shutil.which(_TOOL)
    if found is None:
        return CheckItem(False, f"{_TOOL} not found on PATH", INSTALL_FIX)
    try:
        result = subprocess.run(
            [found, "--version"],
            capture_output=True,
            text=True,
            timeout=_VERSION_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return CheckItem(False, f"{_TOOL} --version failed: {error}", INSTALL_FIX)
    output = result.stdout.strip() or result.stderr.strip()
    if result.returncode != 0:
        return CheckItem(
            False,
            f"{_TOOL} --version exited {result.returncode}: {output}",
            INSTALL_FIX,
        )
    return CheckItem(True, f"{_TOOL} {output}", "")
