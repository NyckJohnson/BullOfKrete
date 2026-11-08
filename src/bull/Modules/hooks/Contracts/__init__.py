"""hooks contract: provider-neutral hook events and decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol


class HookKind(Enum):
    SESSION_START = "session-start"
    BEFORE_AGENT = "before-agent"
    BEFORE_SHELL = "before-shell"
    BEFORE_EDIT = "before-edit"
    BEFORE_READ = "before-read"
    AGENT_END = "agent-end"


@dataclass(frozen=True)
class HookEvent:
    kind: HookKind
    cwd: Path
    agent: str | None  # subagent making the call; None for the orchestrator
    target_agent: str | None  # BEFORE_AGENT: the subagent type being launched
    prompt: str | None
    command: str | None
    paths: tuple[Path, ...]


@dataclass(frozen=True)
class HookDecision:
    allow: bool
    message: str  # block reason, or context text (session start)


class Hooks(Protocol):
    def handle(self, event: HookEvent) -> HookDecision: ...
    def merge_targets(self, command: str) -> list[str]: ...
