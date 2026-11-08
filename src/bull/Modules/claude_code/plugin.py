"""The Claude Code provider: plugin rendering and the provider seam's entry points."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from bull.Modules.claude_code.Contracts import HookOutput, Provider, StatusLineInput
from bull.Modules.foundation.Contracts import AppLayout
from bull.Modules.hooks.Contracts import HookDecision, HookEvent, HookKind
from bull.Modules.settings.Contracts import Settings
from bull.Modules.stacks.Contracts import CheckItem


class LiveProvider(Provider):
    def render_plugin(self, dest: Path, settings: Settings, version: str) -> Path:
        raise NotImplementedError(f"{type(self).__name__}.render_plugin")

    def launch_argv(self, app: AppLayout, extra: Sequence[str]) -> list[str]:
        raise NotImplementedError(f"{type(self).__name__}.launch_argv")

    def tool_check(self) -> CheckItem:
        raise NotImplementedError(f"{type(self).__name__}.tool_check")

    def parse_hook(self, kind: HookKind, raw: str) -> HookEvent:
        raise NotImplementedError(f"{type(self).__name__}.parse_hook")

    def hook_output(self, kind: HookKind, decision: HookDecision) -> HookOutput:
        raise NotImplementedError(f"{type(self).__name__}.hook_output")

    def parse_statusline(self, raw: str) -> StatusLineInput:
        raise NotImplementedError(f"{type(self).__name__}.parse_statusline")

    def app_files(self, app: AppLayout) -> dict[Path, str]:
        raise NotImplementedError(f"{type(self).__name__}.app_files")
