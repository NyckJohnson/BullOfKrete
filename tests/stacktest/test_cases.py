"""Tests for `bull.Modules.stacktest.cases` (`load_cases`)."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from bull.Modules.stacks.Contracts import Stack, StackError
from bull.Modules.stacks.mocks import sample_stack
from bull.Modules.stacktest.cases import load_cases
from bull.Modules.stacktest.Contracts import Case


def _stack(tmp_path: Path) -> Stack:
    home = tmp_path / "fixture"
    home.mkdir()
    return replace(sample_stack(), home=home)


def _write(stack: Stack, data: object) -> None:
    text = data if isinstance(data, str) else json.dumps(data)
    (stack.home / "cases.json").write_text(text)


def _doc(*cases: object, **extra: object) -> dict[str, object]:
    return {"format": 1, "layout": {"app/": "."}, "cases": list(cases), **extra}


def _good(**over: object) -> dict[str, object]:
    case: dict[str, object] = {
        "id": "clean",
        "run": ["gates", "counter"],
        "expect": {"verdict": "pass"},
    }
    case.update(over)
    return case


def test_parses_a_valid_case_into_case_value(tmp_path: Path) -> None:
    stack = _stack(tmp_path)
    _write(stack, _doc(_good(expect={"verdict": "pass", "recorded": True})))
    cases = load_cases(stack)
    assert len(cases) == 1
    case = cases[0]
    assert isinstance(case, Case)
    assert case.id == "clean"
    assert case.run == ("gates", "counter")
    assert case.expect == {"verdict": "pass", "recorded": True}
    assert case.then is None


def test_case_without_change_has_empty_change(tmp_path: Path) -> None:
    stack = _stack(tmp_path)
    _write(stack, _doc(_good()))
    assert dict(load_cases(stack)[0].change) == {}


def test_cases_keep_file_order(tmp_path: Path) -> None:
    stack = _stack(tmp_path)
    _write(stack, _doc(_good(id="b"), _good(id="a"), _good(id="c")))
    assert [c.id for c in load_cases(stack)] == ["b", "a", "c"]


def test_empty_cases_list_gives_no_cases(tmp_path: Path) -> None:
    stack = _stack(tmp_path)
    _write(stack, _doc())
    assert load_cases(stack) == []


def test_change_add_replace_and_delete_are_kept(tmp_path: Path) -> None:
    stack = _stack(tmp_path)
    change = {
        "add": {"tests/new.test": "ok\n"},
        "replace": {"tests/counter/a.test": "fail one\n"},
        "delete": ["src/old.fx"],
    }
    _write(stack, _doc(_good(change=change)))
    got = load_cases(stack)[0].change
    assert got["add"] == {"tests/new.test": "ok\n"}
    assert got["replace"] == {"tests/counter/a.test": "fail one\n"}
    assert list(got["delete"]) == ["src/old.fx"]


def test_nested_then_is_parsed_as_case(tmp_path: Path) -> None:
    stack = _stack(tmp_path)
    then = {"run": ["gates", "--failed"], "expect": {"verdict": "fail", "ran": 1}}
    _write(stack, _doc(_good(id="failing-test", then=then)))
    parent = load_cases(stack)[0]
    assert isinstance(parent.then, Case)
    assert parent.then.run == ("gates", "--failed")
    assert parent.then.expect == {"verdict": "fail", "ran": 1}
    assert parent.then.then is None


def test_then_can_nest_further(tmp_path: Path) -> None:
    stack = _stack(tmp_path)
    inner = {"run": ["status"], "expect": {"verdict": "pass"}}
    outer = {"run": ["gates"], "expect": {"verdict": "fail"}, "then": inner}
    _write(stack, _doc(_good(then=outer)))
    parent = load_cases(stack)[0]
    assert parent.then is not None
    assert parent.then.then is not None
    assert parent.then.then.run == ("status",)


def test_dirty_case_is_accepted(tmp_path: Path) -> None:
    stack = _stack(tmp_path)
    _write(stack, _doc(_good(dirty=True, change={"add": {"a.fx": "x"}})))
    case = load_cases(stack)[0]
    assert case.id == "clean"
    assert case.run == ("gates", "counter")


def test_missing_cases_file_raises_stack_error(tmp_path: Path) -> None:
    with pytest.raises(StackError):
        load_cases(_stack(tmp_path))


@pytest.mark.parametrize("text", ["{not json", "", "[1, 2"])
def test_bad_json_raises_stack_error_with_reason(tmp_path: Path, text: str) -> None:
    stack = _stack(tmp_path)
    _write(stack, text)
    with pytest.raises(StackError) as info:
        load_cases(stack)
    assert str(info.value)


@pytest.mark.parametrize("doc", [[], "text", 3, None])
def test_top_level_not_an_object_raises(tmp_path: Path, doc: object) -> None:
    stack = _stack(tmp_path)
    _write(stack, json.dumps(doc))
    with pytest.raises(StackError):
        load_cases(stack)


@pytest.mark.parametrize("fmt", [2, 0, "1", None])
def test_wrong_format_raises_naming_format(tmp_path: Path, fmt: object) -> None:
    stack = _stack(tmp_path)
    _write(stack, {"format": fmt, "cases": []})
    with pytest.raises(StackError, match="format"):
        load_cases(stack)


def test_missing_format_raises(tmp_path: Path) -> None:
    stack = _stack(tmp_path)
    _write(stack, {"cases": []})
    with pytest.raises(StackError, match="format"):
        load_cases(stack)


def test_missing_cases_key_raises(tmp_path: Path) -> None:
    stack = _stack(tmp_path)
    _write(stack, {"format": 1})
    with pytest.raises(StackError, match="cases"):
        load_cases(stack)


def test_cases_not_a_list_raises(tmp_path: Path) -> None:
    stack = _stack(tmp_path)
    _write(stack, {"format": 1, "cases": {"id": "x"}})
    with pytest.raises(StackError, match="cases"):
        load_cases(stack)


def test_case_not_an_object_raises(tmp_path: Path) -> None:
    stack = _stack(tmp_path)
    _write(stack, _doc("clean"))
    with pytest.raises(StackError):
        load_cases(stack)


@pytest.mark.parametrize("missing", ["id", "run", "expect"])
def test_case_missing_required_field_raises_naming_it(
    tmp_path: Path, missing: str
) -> None:
    stack = _stack(tmp_path)
    case = _good()
    del case[missing]
    _write(stack, _doc(case))
    with pytest.raises(StackError, match=missing):
        load_cases(stack)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", 5),
        ("id", ""),
        ("run", "gates counter"),
        ("run", ["gates", 3]),
        ("run", {"a": 1}),
        ("expect", ["verdict"]),
        ("expect", "pass"),
        ("change", ["add"]),
        ("change", "x"),
    ],
)
def test_case_field_of_wrong_type_raises_naming_it(
    tmp_path: Path, field: str, value: object
) -> None:
    stack = _stack(tmp_path)
    _write(stack, _doc(_good(**{field: value})))
    with pytest.raises(StackError, match=field):
        load_cases(stack)


def test_then_missing_run_raises(tmp_path: Path) -> None:
    stack = _stack(tmp_path)
    _write(stack, _doc(_good(then={"expect": {"verdict": "pass"}})))
    with pytest.raises(StackError, match="run"):
        load_cases(stack)


def test_then_missing_expect_raises(tmp_path: Path) -> None:
    stack = _stack(tmp_path)
    _write(stack, _doc(_good(then={"run": ["gates"]})))
    with pytest.raises(StackError, match="expect"):
        load_cases(stack)


def test_then_not_an_object_raises(tmp_path: Path) -> None:
    stack = _stack(tmp_path)
    _write(stack, _doc(_good(then="gates")))
    with pytest.raises(StackError):
        load_cases(stack)


def test_error_in_a_later_case_still_raises(tmp_path: Path) -> None:
    stack = _stack(tmp_path)
    bad = _good(id="second")
    del bad["run"]
    _write(stack, _doc(_good(), bad))
    with pytest.raises(StackError, match="run"):
        load_cases(stack)
