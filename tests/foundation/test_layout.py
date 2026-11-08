"""Tests for `bull.Modules.foundation.layout`."""

from __future__ import annotations

from pathlib import Path

import pytest

from bull.Modules.foundation.layout import LiveLayouts


def test_at_builds_every_app_folder_path(tmp_path: Path) -> None:
    layout = LiveLayouts().at(tmp_path)
    root = tmp_path.resolve()
    bull = root / ".bull"
    assert layout.root == root
    assert layout.bull_dir == bull
    assert layout.config_file == bull / "config.toml"
    assert layout.parts_dir == bull / "parts"
    assert layout.status_file == bull / "status.json"
    assert layout.backlog_file == bull / "backlog.json"
    assert layout.usage_file == bull / "usage.json"
    assert layout.events_file == bull / "events.jsonl"
    assert layout.passes_dir == bull / "passes"
    assert layout.results_dir == bull / "results"
    assert layout.plugin_dir == bull / "plugin"
    assert layout.run_dir == bull / "run"
    assert layout.memo_file == root / "docs" / "outline.md"
    assert layout.api_dir == root / "docs" / "api"
    assert layout.features_dir == root / "docs" / "features"
    assert layout.interfaces_dir == root / "interfaces"


def test_at_resolves_root_to_absolute_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "app").mkdir()
    monkeypatch.chdir(tmp_path)
    layout = LiveLayouts().at(Path("app"))
    assert layout.root.is_absolute()
    assert layout.root == (tmp_path / "app").resolve()
    assert layout.status_file.is_absolute()


def test_at_does_not_require_the_folder_to_exist(tmp_path: Path) -> None:
    layout = LiveLayouts().at(tmp_path / "missing")
    assert layout.root == (tmp_path / "missing").resolve()


def _make_app(root: Path) -> None:
    (root / ".bull").mkdir(parents=True)
    (root / ".bull" / "status.json").write_text("{}\n")


def test_find_returns_layout_when_start_holds_status_file(tmp_path: Path) -> None:
    _make_app(tmp_path)
    found = LiveLayouts().find(tmp_path)
    assert found is not None
    assert found.root == tmp_path.resolve()


def test_find_walks_up_to_the_nearest_app_folder(tmp_path: Path) -> None:
    _make_app(tmp_path)
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    found = LiveLayouts().find(deep)
    assert found is not None
    assert found.root == tmp_path.resolve()
    assert found == LiveLayouts().at(tmp_path)


def test_find_prefers_the_nearest_of_nested_apps(tmp_path: Path) -> None:
    _make_app(tmp_path)
    inner = tmp_path / "inner"
    _make_app(inner)
    start = inner / "src"
    start.mkdir()
    found = LiveLayouts().find(start)
    assert found is not None
    assert found.root == inner.resolve()


def test_find_returns_none_when_no_app_above(tmp_path: Path) -> None:
    start = tmp_path / "a" / "b"
    start.mkdir(parents=True)
    assert LiveLayouts().find(start) is None


def test_find_ignores_bull_folder_without_status_file(tmp_path: Path) -> None:
    (tmp_path / ".bull").mkdir()
    assert LiveLayouts().find(tmp_path) is None


def test_user_config_dir_uses_xdg_config_home_when_absolute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    assert LiveLayouts().user_config_dir() == tmp_path / "cfg" / "bull"


def test_user_config_dir_defaults_to_dot_config_under_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert LiveLayouts().user_config_dir() == tmp_path / ".config" / "bull"


@pytest.mark.parametrize("value", ["relative/path", "", "."])
def test_user_config_dir_ignores_relative_xdg_value(
    value: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", value)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert LiveLayouts().user_config_dir() == tmp_path / ".config" / "bull"


def test_user_data_dir_uses_xdg_data_home_when_absolute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    assert LiveLayouts().user_data_dir() == tmp_path / "data" / "bull"


def test_user_data_dir_defaults_to_local_share_under_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert LiveLayouts().user_data_dir() == tmp_path / ".local" / "share" / "bull"


@pytest.mark.parametrize("value", ["relative/path", "", "."])
def test_user_data_dir_ignores_relative_xdg_value(
    value: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", value)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert LiveLayouts().user_data_dir() == tmp_path / ".local" / "share" / "bull"


def test_machine_local_ignores_lists_the_six_lines_in_order() -> None:
    assert LiveLayouts().machine_local_ignores() == [
        ".bull/usage.json",
        ".bull/events.jsonl",
        ".bull/passes/",
        ".bull/results/",
        ".bull/plugin/",
        ".bull/run/",
    ]
