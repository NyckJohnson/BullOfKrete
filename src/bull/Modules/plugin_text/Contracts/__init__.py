"""plugin_text contract: the plugin's Markdown files and agent definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class PluginFile:
    path: str  # path relative to the plugin root, e.g. "agents/reviewer.md"
    text: str


@dataclass(frozen=True)
class AgentDoc:
    name: str
    description: str
    tools: tuple[str, ...]
    model_setting: str  # "models.<name>"


class PluginText(Protocol):
    def files(self) -> list[PluginFile]: ...
    def agents(self) -> list[AgentDoc]: ...
    def orchestrator(self) -> str: ...
