"""The plugin's Markdown files, read from this module's folder."""

from __future__ import annotations

from bull.Modules.plugin_text.Contracts import AgentDoc, PluginFile, PluginText


class LivePluginText(PluginText):
    def files(self) -> list[PluginFile]:
        raise NotImplementedError(f"{type(self).__name__}.files")

    def agents(self) -> list[AgentDoc]:
        raise NotImplementedError(f"{type(self).__name__}.agents")

    def orchestrator(self) -> str:
        raise NotImplementedError(f"{type(self).__name__}.orchestrator")
