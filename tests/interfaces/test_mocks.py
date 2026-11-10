"""Tests for `bull.Modules.interfaces.mocks`."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from bull.Modules.foundation.mocks import sample_layout
from bull.Modules.interfaces.Contracts import Interfaces
from bull.Modules.interfaces.mocks import SAMPLE_INTERFACE, MockInterfaces
from bull.Modules.memo.Contracts import Memo, SideRef
from bull.Modules.stacks.Contracts import Role


def _memo() -> Memo:
    return Memo(
        build_order=(),
        modules=(),
        journeys=(),
        interfaces=(SAMPLE_INTERFACE,),
        parts=(),
        unmapped_reference_tests=(),
        legacy=None,
    )


def test_mock_satisfies_interfaces_protocol() -> None:
    mock: Interfaces = MockInterfaces()
    assert isinstance(mock, MockInterfaces)


def test_sample_interface_is_journey_seven_tally_events() -> None:
    assert SAMPLE_INTERFACE.name == "TallyEvents"
    assert SAMPLE_INTERFACE.provider == SideRef("cli", "Export")
    assert SAMPLE_INTERFACE.consumers == (SideRef("web", "Import"),)


def test_for_module_gives_provider_role_to_provider() -> None:
    assert MockInterfaces().for_module(_memo(), "Export") == [
        (SAMPLE_INTERFACE, Role.PROVIDER)
    ]


def test_for_module_gives_consumer_role_to_consumer() -> None:
    assert MockInterfaces().for_module(_memo(), "Import") == [
        (SAMPLE_INTERFACE, Role.CONSUMER)
    ]


def test_for_module_unrelated_module_is_empty() -> None:
    assert MockInterfaces().for_module(_memo(), "Other") == []


def test_problems_empty_by_default_and_follows_found_problems() -> None:
    mock = MockInterfaces()
    app = sample_layout(Path("/app"))
    assert mock.problems(app, _memo()) == []
    mock.found_problems = ["interface X: file y not found"]
    assert mock.problems(app, _memo()) == ["interface X: file y not found"]


def test_check_module_provider_result_is_ok_in_provider_part() -> None:
    results = MockInterfaces().check_module(
        sample_layout(Path("/app")), _memo(), "Export"
    )
    assert len(results) == 1
    assert results[0].interface == "TallyEvents"
    assert results[0].part == "cli"
    assert results[0].module == "Export"
    assert results[0].role is Role.PROVIDER
    assert results[0].ok


def test_check_module_consumer_result_is_in_consumer_part() -> None:
    results = MockInterfaces().check_module(
        sample_layout(Path("/app")), _memo(), "Import"
    )
    assert [(r.part, r.role, r.ok) for r in results] == [("web", Role.CONSUMER, True)]


def test_check_module_unrelated_module_is_empty() -> None:
    assert (
        MockInterfaces().check_module(sample_layout(Path("/app")), _memo(), "Other")
        == []
    )


def test_check_module_uses_overridden_entries() -> None:
    mock = MockInterfaces()
    mock.entries = [replace(SAMPLE_INTERFACE, provider=SideRef("api", "Serve"))]
    results = mock.check_module(sample_layout(Path("/app")), _memo(), "Serve")
    assert [r.part for r in results] == ["api"]


def test_parts_to_run_is_web_for_cli_and_empty_otherwise() -> None:
    mock = MockInterfaces()
    assert mock.parts_to_run(_memo(), "cli") == ["web"]
    assert mock.parts_to_run(_memo(), "web") == []


def test_calls_are_recorded_in_order() -> None:
    mock = MockInterfaces()
    memo = _memo()
    mock.for_module(memo, "Export")
    mock.parts_to_run(memo, "cli")
    assert [name for name, _ in mock.calls] == ["for_module", "parts_to_run"]
    assert mock.calls[0][1] == (memo, "Export")
