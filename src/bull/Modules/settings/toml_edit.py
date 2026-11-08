"""Line-preserving edits of a settings TOML file.

The file is scanned line by line, tracking the current `[table]` header. A value may span several
lines (multi-line strings and arrays); its extent is the fewest lines that parse as a TOML value,
so continuation lines are never mistaken for keys or headers.
"""

from __future__ import annotations

import os
import re
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path

from bull.Modules.foundation.Contracts import BullError
from bull.Modules.settings.Contracts import SettingValue

_BARE_KEY = re.compile(r"[A-Za-z0-9_-]+")
_BASIC_KEY = re.compile(r'"(?:[^"\\\n]|\\.)*"')
_LITERAL_KEY = re.compile(r"'[^'\n]*'")
_NEW_FILE_TEXT = "format = 1\n"


@dataclass(frozen=True)
class _Header:
    index: int  # 0-based line index
    table: tuple[str, ...]
    is_array: bool


@dataclass(frozen=True)
class _Assignment:
    first: int  # 0-based index of the key's line
    last: int  # 0-based index of the value's last line
    key: tuple[str, ...]  # full key, table included
    value_start: int  # offset of the value in the first line


def _parse_key(line: str, pos: int) -> tuple[tuple[str, ...], int] | None:
    """Parse a (dotted) key at `pos`; returns its segments and the offset after it."""
    segments: list[str] = []
    while True:
        while pos < len(line) and line[pos] in " \t":
            pos += 1
        match = (
            _BARE_KEY.match(line, pos)
            or _BASIC_KEY.match(line, pos)
            or _LITERAL_KEY.match(line, pos)
        )
        if match is None:
            return None
        text = match.group(0)
        if text[0] == '"':
            try:
                decoded = tomllib.loads(f"k = {text}")["k"]
            except tomllib.TOMLDecodeError:
                return None
            segments.append(str(decoded))
        elif text[0] == "'":
            segments.append(text[1:-1])
        else:
            segments.append(text)
        pos = match.end()
        while pos < len(line) and line[pos] in " \t":
            pos += 1
        if pos < len(line) and line[pos] == ".":
            pos += 1
            continue
        return tuple(segments), pos


def _parses_as_value(value_text: str) -> bool:
    try:
        tomllib.loads("x = " + value_text)
    except tomllib.TOMLDecodeError:
        return False
    return True


def _value_end(lines: list[str], first: int, value_start: int) -> int:
    """Index of the last line of the value starting at `value_start` in `lines[first]`."""
    text = lines[first][value_start:]
    for last in range(first, len(lines)):
        if last > first:
            text += lines[last]
        if _parses_as_value(text):
            return last
    return first  # malformed value: treat it as one line


def _scan(lines: list[str]) -> tuple[list[_Header], list[_Assignment]]:
    headers: list[_Header] = []
    assignments: list[_Assignment] = []
    table: tuple[str, ...] = ()
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            index += 1
            continue
        if stripped.startswith("["):
            is_array = stripped.startswith("[[")
            opening = line.index("[") + (2 if is_array else 1)
            parsed = _parse_key(line, opening)
            if parsed is not None:
                table = parsed[0]
                headers.append(_Header(index, table, is_array))
            index += 1
            continue
        parsed = _parse_key(line, 0)
        if parsed is None or parsed[1] >= len(line) or line[parsed[1]] != "=":
            index += 1
            continue
        key, pos = parsed
        value_start = pos + 1
        while value_start < len(line) and line[value_start] in " \t":
            value_start += 1
        last = _value_end(lines, index, value_start)
        assignments.append(_Assignment(index, last, table + key, value_start))
        index = last + 1
    return headers, assignments


def _lines(text: str) -> list[str]:
    return text.splitlines(keepends=True)


def _split(key: str) -> tuple[str, ...]:
    return tuple(key.split("."))


def find_line(text: str, key: str) -> int:
    """1-based line of `key`'s assignment in `text`; else the line of its nearest table header
    (`[models]` for `models.x`); 0 when neither is in the file. Comments never match."""
    segments = _split(key)
    headers, assignments = _scan(_lines(text))
    for assignment in assignments:
        if assignment.key == segments:
            return assignment.first + 1
    for size in range(len(segments), 0, -1):
        for header in headers:
            if header.table == segments[:size]:
                return header.index + 1
    return 0


def _render_key(segments: tuple[str, ...]) -> str:
    return ".".join(s if _BARE_KEY.fullmatch(s) else _render_str(s) for s in segments)


def _render_str(value: str) -> str:
    out = ['"']
    for char in value:
        if char == '"':
            out.append('\\"')
        elif char == "\\":
            out.append("\\\\")
        elif char == "\n":
            out.append("\\n")
        elif char == "\t":
            out.append("\\t")
        elif char == "\r":
            out.append("\\r")
        elif ord(char) < 0x20 or ord(char) == 0x7F:
            out.append(f"\\u{ord(char):04X}")
        else:
            out.append(char)
    out.append('"')
    return "".join(out)


def _render_value(value: SettingValue) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return _render_str(value)
    return "[" + ", ".join(_render_str(item) for item in value) + "]"


def _trailing_comment(line: str, value_start: int) -> str:
    """The comment after a one-line value (with the spaces before it), or ""."""
    body = line[value_start:].rstrip("\r\n")
    for match in re.finditer("#", body):
        value = body[: match.start()]
        if _parses_as_value(value):
            return body[len(value.rstrip()) :]
    return ""


def _line_ending(line: str) -> str:
    return line[len(line.rstrip("\r\n")) :]


def _replace(lines: list[str], assignment: _Assignment, rendered: str) -> list[str]:
    first = lines[assignment.first]
    comment = ""
    if assignment.first == assignment.last:
        comment = _trailing_comment(first, assignment.value_start)
    ending = _line_ending(lines[assignment.last])
    new_line = first[: assignment.value_start] + rendered + comment + ending
    return lines[: assignment.first] + [new_line] + lines[assignment.last + 1 :]


def _insert_index(lines: list[str], start: int, end: int, fallback: int) -> int:
    """After the last non-blank, non-comment line in lines[start:end]; else `fallback`."""
    for index in range(end - 1, start - 1, -1):
        stripped = lines[index].strip()
        if stripped and not stripped.startswith("#"):
            return index + 1
    return fallback


def _insert(lines: list[str], at: int, new_line: str) -> list[str]:
    out = list(lines)
    if at > 0 and not out[at - 1].endswith("\n"):
        out[at - 1] += "\n"
    out.insert(at, new_line + "\n")
    return out


def set_key(text: str, key: str, value: SettingValue) -> str:
    """`text` with `key` set to `value`, every other line kept exactly.

    Replaces the key's existing assignment (keeping its trailing comment); else adds it at the
    end of its table's section when the file has a `[table]` for it; else adds it as a dotted
    key at the end of the top-level keys (before the first table header).

    Raises:
        BullError: the edited text would not be valid TOML (e.g. the file is already invalid, or
            the key's table is written as an inline table).
    """
    segments = _split(key)
    rendered = _render_value(value)
    lines = _lines(text)
    headers, assignments = _scan(lines)
    match = next((a for a in assignments if a.key == segments), None)
    if match is not None:
        out = _replace(lines, match, rendered)
    else:
        out = _add(lines, headers, segments, rendered)
    result = "".join(out)
    try:
        tomllib.loads(result)
    except tomllib.TOMLDecodeError as error:
        raise BullError(
            f"cannot set {key}: the edited file would not be valid TOML ({error})",
            fix="fix the file by hand, then try again",
        ) from error
    return result


def _add(
    lines: list[str], headers: list[_Header], segments: tuple[str, ...], rendered: str
) -> list[str]:
    tables = [h for h in headers if not h.is_array]
    for size in range(len(segments) - 1, 0, -1):
        header = next((h for h in tables if h.table == segments[:size]), None)
        if header is None:
            continue
        end = next((h.index for h in headers if h.index > header.index), len(lines))
        at = _insert_index(lines, header.index + 1, end, header.index + 1)
        return _insert(lines, at, f"{_render_key(segments[size:])} = {rendered}")
    end = headers[0].index if headers else len(lines)
    at = _insert_index(lines, 0, end, end)
    return _insert(lines, at, f"{_render_key(segments)} = {rendered}")


def create_if_missing(path: Path) -> None:
    """Create `path` (and its folders) holding `format = 1` when it doesn't exist; written
    atomically (temp file + rename). An existing file is left untouched.

    Raises:
        BullError: the file or its folder couldn't be written.
    """
    if path.exists():
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(_NEW_FILE_TEXT)
            os.replace(temp_name, path)
        except BaseException:
            Path(temp_name).unlink(missing_ok=True)
            raise
    except OSError as error:
        raise BullError(f"cannot create {path}: {error.strerror or error}") from error
