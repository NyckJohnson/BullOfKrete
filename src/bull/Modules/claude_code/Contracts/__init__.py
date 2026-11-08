"""claude_code contract: the provider seam."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from bull.Modules.foundation.Contracts import AppLayout
from bull.Modules.hooks.Contracts import HookDecision, HookEvent, HookKind
from bull.Modules.settings.Contracts import Settings
from bull.Modules.stacks.Contracts import CheckItem
from bull.Modules.usage.Contracts import UsageSample


@dataclass(frozen=True)
class HookOutput:
    stdout: str
    stderr: str
    exit_code: int


@dataclass(frozen=True)
class StatusLineInput:
    cwd: Path
    usage: UsageSample | None


class Provider(Protocol):
    name: str

    def render_plugin(self, dest: Path, settings: Settings, version: str) -> Path: ...
    def launch_argv(self, app: AppLayout, extra: Sequence[str]) -> list[str]: ...
    def tool_check(self) -> CheckItem: ...
    def parse_hook(self, kind: HookKind, raw: str) -> HookEvent: ...
    def hook_output(self, kind: HookKind, decision: HookDecision) -> HookOutput: ...
    def parse_statusline(self, raw: str) -> StatusLineInput: ...
    def app_files(self, app: AppLayout) -> dict[Path, str]: ...
