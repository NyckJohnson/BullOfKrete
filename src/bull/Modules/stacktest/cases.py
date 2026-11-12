"""Parses a stack's `cases.json`."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import cast

from bull.Modules.stacks.Contracts import Stack, StackError
from bull.Modules.stacktest.Contracts import Case

_FORMAT = 1
_CHANGE_TEXT_KEYS = ("add", "replace")


def load_cases(stack: Stack) -> list[Case]:
    """Parse `<stack.home>/cases.json` into `Case` values, in file order.

    A nested `then` becomes a `Case` whose id is `<parent id>/then`. A case's
    `"dirty": true` is carried in its `change` mapping as `"dirty": True`.

    Raises:
        StackError: the file is missing or unreadable, is not valid JSON, or does
            not have the shape described in the memo's cases.json data model;
            the message names the offending field.
    """
    path = stack.home / "cases.json"
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise StackError(f"{path}: missing cases.json") from error
    except (OSError, UnicodeDecodeError) as error:
        raise StackError(f"{path}: cannot read cases.json: {error}") from error
    try:
        data: object = json.loads(text)
    except json.JSONDecodeError as error:
        raise StackError(f"{path}: invalid JSON: {error}") from error
    if not isinstance(data, dict):
        raise StackError(f"{path}: top level must be a JSON object")
    doc = cast("dict[str, object]", data)
    fmt = doc.get("format")
    if "format" not in doc:
        raise StackError(f"{path}: missing `format` (expected {_FORMAT})")
    if isinstance(fmt, bool) or fmt != _FORMAT:
        raise StackError(f"{path}: unsupported format {fmt!r} (expected {_FORMAT})")
    if "cases" not in doc:
        raise StackError(f"{path}: missing `cases`")
    raw_cases = doc["cases"]
    if not isinstance(raw_cases, list):
        raise StackError(f"{path}: `cases` must be a list")
    return [
        _case(raw, f"cases[{index}]", None, path.name)
        for index, raw in enumerate(cast("list[object]", raw_cases))
    ]


def _case(raw: object, where: str, parent_id: str | None, file: str) -> Case:
    """Parse one case object; `parent_id` is set for a `then` case (no own id)."""
    if not isinstance(raw, dict):
        raise StackError(f"{file}: {where} must be an object")
    entry = cast("dict[str, object]", raw)
    if parent_id is None:
        case_id = _required(entry, "id", where, file)
        if not isinstance(case_id, str) or not case_id:
            raise StackError(f"{file}: {where}: `id` must be a non-empty string")
        where = f"case `{case_id}`"
    else:
        case_id = f"{parent_id}/then"

    run = _required(entry, "run", where, file)
    if not isinstance(run, list) or not all(isinstance(arg, str) for arg in run):
        raise StackError(f"{file}: {where}: `run` must be a list of strings")

    expect = _required(entry, "expect", where, file)
    if not isinstance(expect, dict):
        raise StackError(f"{file}: {where}: `expect` must be an object")

    change = _change(entry.get("change", {}), where, file)
    dirty = entry.get("dirty", False)
    if not isinstance(dirty, bool):
        raise StackError(f"{file}: {where}: `dirty` must be true or false")
    if dirty:
        change["dirty"] = True

    then: Case | None = None
    if "then" in entry:
        then = _case(entry["then"], f"{where} `then`", case_id, file)

    return Case(
        id=case_id,
        change=change,
        run=tuple(cast("list[str]", run)),
        expect=dict(cast("dict[str, object]", expect)),
        then=then,
    )


def _required(entry: Mapping[str, object], key: str, where: str, file: str) -> object:
    if key not in entry:
        raise StackError(f"{file}: {where}: missing `{key}`")
    return entry[key]


def _change(raw: object, where: str, file: str) -> dict[str, object]:
    """Validate a `change` object: `add`/`replace` (path → text), `delete` (paths)."""
    if not isinstance(raw, dict):
        raise StackError(f"{file}: {where}: `change` must be an object")
    change = cast("dict[str, object]", raw)
    result: dict[str, object] = {}
    for key, value in change.items():
        if key in _CHANGE_TEXT_KEYS:
            if not isinstance(value, dict) or not all(
                isinstance(k, str) and isinstance(v, str)
                for k, v in cast("dict[object, object]", value).items()
            ):
                raise StackError(
                    f"{file}: {where}: `change.{key}` must map paths to text"
                )
            result[key] = dict(cast("dict[str, str]", value))
        elif key == "delete":
            if not isinstance(value, list) or not all(
                isinstance(p, str) for p in cast("list[object]", value)
            ):
                raise StackError(
                    f"{file}: {where}: `change.delete` must be a list of paths"
                )
            result[key] = tuple(cast("list[str]", value))
        else:
            raise StackError(f"{file}: {where}: unknown `change` key `{key}`")
    return result
