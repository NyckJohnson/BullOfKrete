"""Mocks of the claude_code contract, for tests and previews."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from bull.Modules.claude_code.Contracts import HookOutput, Provider, StatusLineInput
from bull.Modules.foundation.Contracts import AppLayout
from bull.Modules.hooks.Contracts import HookDecision, HookEvent, HookKind
from bull.Modules.settings.Contracts import Settings
from bull.Modules.stacks.Contracts import CheckItem
from bull.Modules.usage.Contracts import UsageSample


class MockProvider(Provider):
    """A provider named `mock`; hook input is read as the event's prompt."""

    def __init__(self) -> None:
        self.name = "mock"
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def render_plugin(self, dest: Path, settings: Settings, version: str) -> Path:
        self.calls.append(("render_plugin", (dest, settings, version)))
        return dest

    def launch_argv(self, app: AppLayout, extra: Sequence[str]) -> list[str]:
        self.calls.append(("launch_argv", (app, tuple(extra))))
        return ["claude", "--plugin-dir", str(app.plugin_dir), *extra]

    def tool_check(self) -> CheckItem:
        self.calls.append(("tool_check", ()))
        return CheckItem(True, "claude 2.1.0 (Claude Code)", "")

    def parse_hook(self, kind: HookKind, raw: str) -> HookEvent:
        self.calls.append(("parse_hook", (kind, raw)))
        return HookEvent(
            kind=kind,
            cwd=Path("/tmp/apps/tally"),
            agent=None,
            target_agent="bull:test-writer" if kind is HookKind.BEFORE_AGENT else None,
            prompt=raw,
            command=None,
            paths=(),
        )

    def hook_output(self, kind: HookKind, decision: HookDecision) -> HookOutput:
        self.calls.append(("hook_output", (kind, decision)))
        if not decision.allow:
            return HookOutput("", decision.message, 2)
        stdout = decision.message if kind is HookKind.SESSION_START else ""
        return HookOutput(stdout, "", 0)

    def parse_statusline(self, raw: str) -> StatusLineInput:
        self.calls.append(("parse_statusline", (raw,)))
        return StatusLineInput(
            cwd=Path("/tmp/apps/tally"),
            usage=UsageSample(
                time=datetime(2026, 11, 7, 12, 0, 0, tzinfo=UTC),
                five_hour=92.0,
                weekly=40.0,
                five_hour_resets=datetime(2026, 11, 7, 15, 0, 0, tzinfo=UTC),
                weekly_resets=None,
            ),
        )

    def app_files(self, app: AppLayout) -> dict[Path, str]:
        self.calls.append(("app_files", (app,)))
        return {
            app.root
            / ".claude"
            / "settings.json": '{\n  "statusLine": "bull statusline"\n}\n',
            app.root / "CLAUDE.md": (
                "<!-- bull:begin -->\n@.bull/plugin/orchestrator.md\n<!-- bull:end -->\n"
            ),
        }
