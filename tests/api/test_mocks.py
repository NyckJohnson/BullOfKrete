"""Tests for `bull.Modules.api.mocks`."""

from __future__ import annotations

from pathlib import Path

from bull.Modules.api.Contracts import ApiCheck, ApiSnapshots, Snapshot
from bull.Modules.api.mocks import MockApiSnapshots, sample_snapshot
from bull.Modules.foundation.Contracts import AppLayout


def _app() -> AppLayout:
    root = Path("/app")
    values = {name: root / name for name in AppLayout.__dataclass_fields__}
    values["api_dir"] = root / "docs" / "api"
    return AppLayout(**values)


def test_mock_satisfies_api_snapshots_protocol() -> None:
    mock: ApiSnapshots = MockApiSnapshots()
    assert isinstance(mock, MockApiSnapshots)


def test_sample_snapshot_default_name_and_files() -> None:
    snap = sample_snapshot()
    assert snap.name == "Counter"
    assert snap.files


def test_sample_snapshot_uses_given_name() -> None:
    assert sample_snapshot("X").name == "X"


def test_current_returns_snapshot_named_for_module() -> None:
    assert MockApiSnapshots().current(_app(), "memo").name == "memo"


def test_check_passes_by_default() -> None:
    check = MockApiSnapshots().check(_app(), "memo")
    assert check == ApiCheck(name="memo", ok=True, stored=True, diff="")


def test_check_returns_configured_failing_result() -> None:
    mock = MockApiSnapshots()
    failing = ApiCheck(name="memo", ok=False, stored=True, diff="-a\n+b")
    mock.result = failing
    assert mock.check(_app(), "memo") is failing


def test_check_interface_passes_by_default() -> None:
    check = MockApiSnapshots().check_interface(_app(), "Iface")
    assert check == ApiCheck(name="Iface", ok=True, stored=True, diff="")


def test_check_interface_returns_configured_failing_result() -> None:
    mock = MockApiSnapshots()
    failing = ApiCheck(name="Iface", ok=False, stored=False, diff="no snapshot")
    mock.result = failing
    assert mock.check_interface(_app(), "Iface") is failing


def test_write_returns_module_snapshot_path_in_api_dir() -> None:
    app = _app()
    assert MockApiSnapshots().write(app, "memo") == app.api_dir / "memo.md"


def test_write_interface_returns_path_under_interfaces() -> None:
    app = _app()
    assert MockApiSnapshots().write_interface(app, "Iface") == (
        app.api_dir / "interfaces" / "Iface.md"
    )


def test_calls_record_each_invocation_in_order() -> None:
    mock = MockApiSnapshots()
    app = _app()
    mock.current(app, "a")
    mock.check(app, "a")
    mock.write(app, "a", "note")
    mock.check_interface(app, "i")
    mock.write_interface(app, "i", None)
    assert [name for name, _ in mock.calls] == [
        "current",
        "check",
        "write",
        "check_interface",
        "write_interface",
    ]
    assert mock.calls[2][1] == (app, "a", "note")
    assert mock.calls[4][1] == (app, "i", None)


def test_calls_start_empty() -> None:
    assert MockApiSnapshots().calls == []


def test_render_starts_with_name_contract_heading() -> None:
    text = MockApiSnapshots().render(Snapshot("Foo", {}))
    assert text.splitlines()[0] == "# Foo contract"


def test_render_lists_each_file_with_fenced_declarations_sorted() -> None:
    snap = Snapshot("Foo", {"b.py": ("pub b",), "a.py": ("pub a1", "pub a2")})
    text = MockApiSnapshots().render(snap)
    assert text.index("## a.py") < text.index("## b.py")
    assert "## a.py\n```\npub a1\npub a2\n```" in text
    assert "## b.py\n```\npub b\n```" in text


def test_render_records_call() -> None:
    mock = MockApiSnapshots()
    snap = sample_snapshot()
    mock.render(snap)
    assert mock.calls == [("render", (snap,))]


def test_parse_returns_a_snapshot_and_records_call() -> None:
    mock = MockApiSnapshots()
    result = mock.parse("# x contract")
    assert isinstance(result, Snapshot)
    assert mock.calls == [("parse", ("# x contract",))]
