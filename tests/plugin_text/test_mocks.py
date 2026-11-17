"""Tests for `bull.Modules.plugin_text.mocks` (MockPluginText)."""

from __future__ import annotations

from bull.Modules.plugin_text.Contracts import AgentDoc, PluginFile
from bull.Modules.plugin_text.mocks import SAMPLE_ORCHESTRATOR, MockPluginText


def test_mock_files_returns_its_sample_files() -> None:
    files = MockPluginText().files()
    assert files
    assert all(isinstance(f, PluginFile) for f in files)
    assert "orchestrator.md" in [f.path for f in files]


def test_mock_agents_returns_its_sample_agents() -> None:
    docs = MockPluginText().agents()
    assert docs
    assert all(isinstance(d, AgentDoc) for d in docs)
    assert all(d.model_setting == f"models.{d.name}" for d in docs)


def test_mock_orchestrator_returns_sample_text() -> None:
    assert MockPluginText().orchestrator() == SAMPLE_ORCHESTRATOR


def test_mock_records_each_call_in_order() -> None:
    mock = MockPluginText()
    mock.files()
    mock.agents()
    mock.orchestrator()
    assert [name for name, _ in mock.calls] == ["files", "agents", "orchestrator"]
