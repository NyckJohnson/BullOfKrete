"""Tests for `bull.Modules.foundation.files`."""

from __future__ import annotations

import os
import secrets
from pathlib import Path

import pytest

from bull.Modules.foundation.Contracts import FileFormatError
from bull.Modules.foundation.files import LiveFiles


def test_read_text_returns_file_contents(tmp_path: Path) -> None:
    target = tmp_path / "a.txt"
    target.write_text("héllo\nworld\n", encoding="utf-8")
    assert LiveFiles().read_text(target) == "héllo\nworld\n"


def test_read_text_returns_none_for_missing_file(tmp_path: Path) -> None:
    assert LiveFiles().read_text(tmp_path / "nope.txt") is None


def test_write_atomic_writes_text(tmp_path: Path) -> None:
    target = tmp_path / "a.txt"
    LiveFiles().write_atomic(target, "hello")
    assert target.read_text(encoding="utf-8") == "hello"


def test_write_atomic_creates_parent_folders(tmp_path: Path) -> None:
    target = tmp_path / "x" / "y" / "a.txt"
    LiveFiles().write_atomic(target, "hi")
    assert target.read_text(encoding="utf-8") == "hi"


def test_write_atomic_replaces_existing_content(tmp_path: Path) -> None:
    target = tmp_path / "a.txt"
    target.write_text("old")
    LiveFiles().write_atomic(target, "new")
    assert target.read_text() == "new"


def test_write_atomic_new_file_honors_the_process_umask(tmp_path: Path) -> None:
    target = tmp_path / "a.txt"
    old = os.umask(0o077)
    try:
        LiveFiles().write_atomic(target, "secret")
    finally:
        os.umask(old)
    assert target.stat().st_mode & 0o077 == 0


def test_write_atomic_keeps_the_mode_of_an_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "a.txt"
    target.write_text("old")
    target.chmod(0o640)
    LiveFiles().write_atomic(target, "new")
    assert target.stat().st_mode & 0o777 == 0o640


def test_write_atomic_leaves_no_extra_files_behind(tmp_path: Path) -> None:
    LiveFiles().write_atomic(tmp_path / "a.txt", "hi")
    assert [p.name for p in tmp_path.iterdir()] == ["a.txt"]


def test_write_atomic_renames_a_temp_file_from_the_same_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "sub" / "a.txt"
    calls: list[tuple[Path, Path]] = []
    real_replace = os.replace

    def spy(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        calls.append((Path(src), Path(dst)))
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", spy)
    LiveFiles().write_atomic(target, "hi")
    assert len(calls) == 1
    src, dst = calls[0]
    assert dst == target
    assert src != target
    assert src.parent == target.parent


def test_interrupted_write_leaves_old_target_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "a.txt"
    target.write_text("old")

    def boom(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        raise OSError("interrupted")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        LiveFiles().write_atomic(target, "new")
    assert target.read_text() == "old"


def test_interrupted_write_does_not_create_a_partial_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "a.txt"

    def boom(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        raise OSError("interrupted")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        LiveFiles().write_atomic(target, "new")
    assert not target.exists()


def test_read_json_parses_a_document(tmp_path: Path) -> None:
    target = tmp_path / "a.json"
    target.write_text('{"a": [1, 2], "b": null}')
    assert LiveFiles().read_json(target) == {"a": [1, 2], "b": None}


def test_read_json_returns_none_for_missing_file(tmp_path: Path) -> None:
    assert LiveFiles().read_json(tmp_path / "nope.json") is None


def test_read_json_invalid_raises_file_format_error_naming_path_and_line(
    tmp_path: Path,
) -> None:
    target = tmp_path / "bad.json"
    target.write_text('{\n  "a": 1,\n  "b": oops\n}\n')
    with pytest.raises(FileFormatError) as info:
        LiveFiles().read_json(target)
    assert str(target) in info.value.message
    assert "3" in info.value.message


def test_read_json_non_utf8_bytes_raise_file_format_error_naming_path(
    tmp_path: Path,
) -> None:
    target = tmp_path / "binary.json"
    target.write_bytes(b"\xff\xfe")
    with pytest.raises(FileFormatError) as info:
        LiveFiles().read_json(target)
    assert str(target) in info.value.message


def test_read_json_empty_file_raises_file_format_error(tmp_path: Path) -> None:
    target = tmp_path / "empty.json"
    target.write_text("")
    with pytest.raises(FileFormatError) as info:
        LiveFiles().read_json(target)
    assert str(target) in info.value.message


def test_write_json_uses_indent_2_sorted_keys_and_trailing_newline(
    tmp_path: Path,
) -> None:
    target = tmp_path / "a.json"
    LiveFiles().write_json(target, {"b": 1, "a": [1, 2]})
    assert target.read_text() == '{\n  "a": [\n    1,\n    2\n  ],\n  "b": 1\n}\n'


def test_write_json_creates_parent_folders(tmp_path: Path) -> None:
    target = tmp_path / "x" / "a.json"
    LiveFiles().write_json(target, {"a": 1})
    assert target.read_text() == '{\n  "a": 1\n}\n'


def test_write_json_round_trips_through_read_json(tmp_path: Path) -> None:
    target = tmp_path / "a.json"
    data = {"z": {"y": [1, "two", None, True]}, "a": 1.5}
    LiveFiles().write_json(target, data)
    assert LiveFiles().read_json(target) == data


def test_write_json_is_atomic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "a.json"
    target.write_text("old")

    def boom(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        raise OSError("interrupted")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        LiveFiles().write_json(target, {"a": 1})
    assert target.read_text() == "old"


def test_append_line_creates_file_with_newline(tmp_path: Path) -> None:
    target = tmp_path / "log.txt"
    LiveFiles().append_line(target, "one")
    assert target.read_text() == "one\n"


def test_append_line_creates_parent_folders(tmp_path: Path) -> None:
    target = tmp_path / "x" / "y" / "log.txt"
    LiveFiles().append_line(target, "one")
    assert target.read_text() == "one\n"


def test_append_line_appends_to_existing_content(tmp_path: Path) -> None:
    target = tmp_path / "log.txt"
    files = LiveFiles()
    files.append_line(target, "one")
    files.append_line(target, "two")
    assert target.read_text() == "one\ntwo\n"


def test_write_atomic_retries_with_a_new_name_when_the_temp_name_is_taken(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "a.txt"
    taken = tmp_path / ".a.txt.aaaaaaaaaaaa.tmp"
    taken.write_text("squatter")
    real_token_hex = secrets.token_hex
    names = iter(["aaaaaaaaaaaa"])

    def fake_token_hex(nbytes: int | None = None) -> str:
        fixed = next(names, None)
        return fixed if fixed is not None else real_token_hex(nbytes)

    monkeypatch.setattr(secrets, "token_hex", fake_token_hex)
    LiveFiles().write_atomic(target, "hello")
    assert target.read_text() == "hello"
    assert taken.read_text() == "squatter"


def test_write_atomic_raises_and_leaves_target_when_every_temp_name_is_taken(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "a.txt"
    target.write_text("old")

    def always_taken(*args: object, **kwargs: object) -> int:
        raise FileExistsError("taken")

    with monkeypatch.context() as patch:
        patch.setattr(os, "open", always_taken)
        with pytest.raises(FileExistsError):
            LiveFiles().write_atomic(target, "new")
    assert target.read_text() == "old"
