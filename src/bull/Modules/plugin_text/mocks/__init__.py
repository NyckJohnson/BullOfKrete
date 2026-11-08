"""Mocks of the plugin_text contract, for tests and previews."""

from __future__ import annotations

from bull.Modules.plugin_text.Contracts import AgentDoc, PluginFile, PluginText

SAMPLE_ORCHESTRATOR = (
    "# bull orchestrator\n\n"
    "## Golden rules\n\n"
    "1. One subagent at a time.\n"
    "2. Files are the memory.\n"
)


class MockPluginText(PluginText):
    """An orchestrator, one command and one agent."""

    def __init__(self) -> None:
        self.plugin_files: list[PluginFile] = [
            PluginFile(
                "agents/reviewer.md",
                "---\nname: reviewer\ndescription: Reviews a unit.\ntools: Read, Grep\n---\n",
            ),
            PluginFile(
                "commands/status.md",
                "---\ndescription: Show pipeline progress.\n---\nRun `bull status`.\n",
            ),
            PluginFile("orchestrator.md", SAMPLE_ORCHESTRATOR),
        ]
        self.agent_docs: list[AgentDoc] = [
            AgentDoc("reviewer", "Reviews a unit.", ("Read", "Grep"), "models.reviewer")
        ]
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def files(self) -> list[PluginFile]:
        self.calls.append(("files", ()))
        return list(self.plugin_files)

    def agents(self) -> list[AgentDoc]:
        self.calls.append(("agents", ()))
        return list(self.agent_docs)

    def orchestrator(self) -> str:
        self.calls.append(("orchestrator", ()))
        return SAMPLE_ORCHESTRATOR
