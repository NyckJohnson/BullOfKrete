"""Tests for `bull.Modules.stacktest.static` (`static`)."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from bull.Modules.stacks.Contracts import (
    OptionalReaders,
    RunCommands,
    Stack,
)
from bull.Modules.stacks.mocks import sample_stack
from bull.Modules.stacktest.Contracts import StackTestReport
from bull.Modules.stacktest.static import static

BASE_IDS = [
    "clean",
    "fast",
    "no-tests",
    "failing-test",
    "build-warning",
    "lint",
    "contract-change",
    "uncovered",
    "exemption",
    "setup-broken",
]
AGENTS = [
    "skeleton-builder",
    "test-writer",
    "code-writer",
    "reviewer",
    "coverage-analyst",
]
READERS = (
    "def contract_declarations(path):\n    return []\n\n"
    "def test_results(results):\n    return None\n\n"
    "def uncovered(part_root, sources, results):\n    raise NotImplementedError\n\n"
    "def check(part_root, settings, adopting):\n    return []\n"
)
STACK_TOML = """format = 1
[stack]
name = "mystack"
title = "My stack"
description = "A stack."
language = "fixture"
kind = "tool"
maturity = "experimental"
source_glob = "*.fx"
test_glob = ["*.test"]
comment = "#"
scaffold = ["src", "tests"]
gitignore = ["results/"]
agents = ["skeleton-builder", "test-writer", "code-writer", "reviewer", "coverage-analyst"]
[settings.source_dir]
type = "str"
default = "src/fx"
description = "Source folder."
[settings.test_dir]
type = "str"
default = "tests"
description = "Test folder."
[gates]
preflight = ["x", "preflight"]
setup = ["x", "setup"]
build_test = ["x", "build-test"]
build_test_fast = ["x", "build-test-fast", "{module}"]
lint = ["x", "lint", "{module}"]
rerun_failed = ["x", "rerun", "{failed_ids}"]
"""


def _cases_json(ids: list[str]) -> str:
    cases = [{"id": i, "run": ["gates"], "expect": {"verdict": "pass"}} for i in ids]
    return json.dumps({"format": 1, "layout": {"app/": "."}, "cases": cases})


def _rules(agents: list[str], extra: list[str] | None = None) -> str:
    heads = ["common", "outline", *agents, *(extra or [])]
    return "".join(f"## {h}\n\nText.\n\n" for h in heads)


def _build(
    tmp_path: Path,
    *,
    ids: list[str] | None = None,
    readers: str = READERS,
    rules: str | None = None,
    setup: str = "Steps.\n\n## For a feature\n\nMore.\n",
    toml: str = STACK_TOML,
) -> Path:
    home = tmp_path / "mystack"
    home.mkdir()
    (home / "stack.toml").write_text(toml)
    (home / "readers.py").write_text(readers)
    (home / "rules.md").write_text(rules if rules is not None else _rules(AGENTS))
    (home / "setup.md").write_text(setup)
    (home / "cases.json").write_text(_cases_json(BASE_IDS if ids is None else ids))
    (home / "fixture").mkdir()
    (home / "fixture" / "a.fx").write_text("x\n")
    return home


def _stack(
    home: Path,
    *,
    journeys: bool = False,
    interfaces: bool = False,
    run: bool = False,
    detect: bool = False,
) -> Stack:
    base = sample_stack("mystack")
    manifest = base.manifest
    gates = replace(manifest.gates, journeys=("x", "journeys") if journeys else None)
    manifest = replace(
        manifest,
        agents=tuple(AGENTS + (["journey-test-writer"] if journeys else [])),
        gates=gates,
        interface_formats=("json-schema",) if interfaces else (),
        run=RunCommands(("s",), ("r",), ("t",), 30.0) if run else None,
    )
    optional = OptionalReaders(
        detect=(lambda p: None) if detect else None,  # type: ignore[arg-type,return-value]
        inventory=None,
        legacy_declarations=None,
        interface_check=None,
    )
    return replace(base, manifest=manifest, home=home, optional=optional)


def _check(home: Path, **kw: bool) -> StackTestReport:
    return static(_stack(home, **kw))


def _mentions(report: StackTestReport, text: str) -> bool:
    return any(text in p for p in report.problems)


def test_complete_stack_passes_with_no_problems(tmp_path: Path) -> None:
    report = _check(_build(tmp_path))
    assert report.problems == ()
    assert report.static is True
    assert report.cases == ()
    assert report.ok is True
    assert report.stack == "mystack"


@pytest.mark.parametrize(
    "name", ["stack.toml", "readers.py", "rules.md", "setup.md", "cases.json"]
)
def test_missing_required_file_is_reported(tmp_path: Path, name: str) -> None:
    home = _build(tmp_path)
    (home / name).unlink()
    report = _check(home)
    assert _mentions(report, name)
    assert report.ok is False


def test_missing_fixture_folder_is_reported(tmp_path: Path) -> None:
    home = _build(tmp_path)
    (home / "fixture" / "a.fx").unlink()
    (home / "fixture").rmdir()
    report = _check(home)
    assert len(report.problems) == 1
    assert "fixture" in report.problems[0]


def test_empty_fixture_folder_is_exactly_one_problem_naming_fixture(
    tmp_path: Path,
) -> None:
    home = _build(tmp_path)
    (home / "fixture" / "a.fx").unlink()
    report = _check(home)
    assert len(report.problems) == 1
    assert "fixture" in report.problems[0]
    assert report.ok is False


def test_fixture_that_is_a_file_is_reported(tmp_path: Path) -> None:
    home = _build(tmp_path)
    (home / "fixture" / "a.fx").unlink()
    (home / "fixture").rmdir()
    (home / "fixture").write_text("not a folder")
    assert _mentions(_check(home), "fixture")


def test_missing_rules_file_alone_is_one_problem(tmp_path: Path) -> None:
    home = _build(tmp_path)
    (home / "rules.md").unlink()
    report = _check(home)
    assert len(report.problems) == 1
    assert "rules.md" in report.problems[0]


def test_missing_setup_file_alone_is_one_problem(tmp_path: Path) -> None:
    home = _build(tmp_path)
    (home / "setup.md").unlink()
    report = _check(home)
    assert len(report.problems) == 1
    assert "setup.md" in report.problems[0]


def test_manifest_with_todo_placeholder_is_one_problem(tmp_path: Path) -> None:
    home = _build(
        tmp_path, toml=STACK_TOML.replace('title = "My stack"', 'title = "TODO"')
    )
    report = _check(home)
    assert report.ok is False
    assert len(report.problems) == 1
    assert "stack.toml" in report.problems[0]


def test_manifest_with_todo_inside_a_list_is_one_problem(tmp_path: Path) -> None:
    toml = STACK_TOML.replace(
        'gitignore = ["results/"]', 'gitignore = ["results/", "TODO"]'
    )
    report = _check(_build(tmp_path, toml=toml))
    assert len(report.problems) == 1
    assert "stack.toml" in report.problems[0]


@pytest.mark.parametrize(
    ("label", "toml"),
    [
        ("format 2", STACK_TOML.replace("format = 1\n", "format = 2\n", 1)),
        ("missing format", STACK_TOML.replace("format = 1\n", "", 1)),
        ("missing gates", STACK_TOML[: STACK_TOML.index("[gates]")]),
        (
            "missing settings.test_dir",
            STACK_TOML.replace(
                '[settings.test_dir]\ntype = "str"\ndefault = "tests"\n'
                'description = "Test folder."\n',
                "",
            ),
        ),
    ],
)
def test_manifest_structural_miss_is_one_problem(
    tmp_path: Path, label: str, toml: str
) -> None:
    assert toml != STACK_TOML, label
    report = _check(_build(tmp_path, toml=toml))
    assert report.ok is False
    assert len(report.problems) == 1, label
    assert "stack.toml" in report.problems[0]


def test_manifest_with_invalid_toml_is_a_problem(tmp_path: Path) -> None:
    home = _build(tmp_path, toml="format = [unclosed")
    report = _check(home)
    assert report.ok is False
    assert _mentions(report, "stack.toml")


def test_manifest_missing_required_key_is_one_problem_naming_key(
    tmp_path: Path,
) -> None:
    home = _build(tmp_path, toml=STACK_TOML.replace('language = "fixture"\n', ""))
    report = _check(home)
    assert report.ok is False
    assert len(report.problems) == 1
    assert "stack.toml" in report.problems[0]
    assert "language" in report.problems[0]


def test_readers_missing_required_function_names_it(tmp_path: Path) -> None:
    readers = READERS.replace("def test_results(results):\n    return None\n\n", "")
    report = _check(_build(tmp_path, readers=readers))
    assert len(report.problems) == 1
    assert "test_results" in report.problems[0]


@pytest.mark.parametrize(
    "func", ["contract_declarations", "test_results", "uncovered", "check"]
)
def test_each_required_reader_function_is_checked(tmp_path: Path, func: str) -> None:
    kept = "".join(
        f"def {n}(*a):\n    return None\n\n"
        for n in ["contract_declarations", "test_results", "uncovered", "check"]
        if n != func
    )
    report = _check(_build(tmp_path, readers=kept))
    assert _mentions(report, func)


def test_readers_is_checked_without_importing_it(tmp_path: Path) -> None:
    readers = "raise RuntimeError('imported')\n\n" + READERS
    report = _check(_build(tmp_path, readers=readers))
    assert report.problems == ()
    assert report.ok is True


def test_readers_importing_missing_package_still_passes(tmp_path: Path) -> None:
    readers = "import no_such_package_anywhere\n" + READERS
    assert _check(_build(tmp_path, readers=readers)).ok is True


def test_readers_with_syntax_error_is_a_problem(tmp_path: Path) -> None:
    report = _check(_build(tmp_path, readers="def broken(:\n"))
    assert report.ok is False
    assert _mentions(report, "readers.py")


@pytest.mark.parametrize("missing", ["common", "outline"])
def test_rules_missing_fixed_section_is_a_problem(tmp_path: Path, missing: str) -> None:
    heads = [a for a in AGENTS]
    text = _rules(heads)
    text = text.replace(f"## {missing}\n", "")
    report = _check(_build(tmp_path, rules=text))
    assert len(report.problems) == 1
    assert missing in report.problems[0]


@pytest.mark.parametrize("agent", AGENTS)
def test_rules_missing_agent_section_names_the_agent(
    tmp_path: Path, agent: str
) -> None:
    report = _check(_build(tmp_path, rules=_rules([a for a in AGENTS if a != agent])))
    assert len(report.problems) == 1
    assert agent in report.problems[0]


def test_rules_section_per_agent_includes_journey_writer_when_manifest_lists_it(
    tmp_path: Path,
) -> None:
    ids = [*BASE_IDS, "journey", "journey-failing"]
    home = _build(tmp_path, ids=ids)
    report = _check(home, journeys=True)
    assert len(report.problems) == 1
    assert "journey-test-writer" in report.problems[0]


def test_rules_extra_sections_are_fine(tmp_path: Path) -> None:
    home = _build(tmp_path, rules=_rules(AGENTS, ["extra"]))
    assert _check(home).ok is True


def test_setup_missing_for_a_feature_section_is_a_problem(tmp_path: Path) -> None:
    report = _check(_build(tmp_path, setup="Steps only.\n"))
    assert len(report.problems) == 1
    assert "For a feature" in report.problems[0]


@pytest.mark.parametrize("missing", BASE_IDS)
def test_cases_missing_required_id_names_it(tmp_path: Path, missing: str) -> None:
    ids = [i for i in BASE_IDS if i != missing]
    report = _check(_build(tmp_path, ids=ids))
    assert len(report.problems) == 1
    assert missing in report.problems[0]


@pytest.mark.parametrize(
    ("flag", "ids"),
    [
        ("journeys", ["journey", "journey-failing"]),
        ("interfaces", ["interface-drift"]),
        ("run", ["run-lifecycle"]),
        ("detect", ["adopt-mode"]),
    ],
)
def test_conditional_ids_are_required_when_capability_present(
    tmp_path: Path, flag: str, ids: list[str]
) -> None:
    rules = _rules(AGENTS + (["journey-test-writer"] if flag == "journeys" else []))
    readers = READERS + (
        "\ndef detect(path):\n    return None\n" if flag == "detect" else ""
    )
    home = _build(tmp_path, rules=rules, readers=readers)
    report = _check(home, **{flag: True})
    for needed in ids:
        assert _mentions(report, needed)
    assert len(report.problems) == len(ids)


@pytest.mark.parametrize(
    ("flag", "ids"),
    [
        ("journeys", ["journey", "journey-failing"]),
        ("interfaces", ["interface-drift"]),
        ("run", ["run-lifecycle"]),
        ("detect", ["adopt-mode"]),
    ],
)
def test_conditional_ids_pass_when_present(
    tmp_path: Path, flag: str, ids: list[str]
) -> None:
    rules = _rules(AGENTS + (["journey-test-writer"] if flag == "journeys" else []))
    readers = READERS + (
        "\ndef detect(path):\n    return None\n" if flag == "detect" else ""
    )
    home = _build(tmp_path, ids=[*BASE_IDS, *ids], rules=rules, readers=readers)
    assert _check(home, **{flag: True}).ok is True


def test_conditional_ids_not_required_without_capability(tmp_path: Path) -> None:
    assert _check(_build(tmp_path)).problems == ()


def test_cases_file_with_bad_json_is_a_problem(tmp_path: Path) -> None:
    home = _build(tmp_path)
    (home / "cases.json").write_text("{nope")
    report = _check(home)
    assert report.ok is False
    assert _mentions(report, "cases.json")


def test_several_misses_give_several_problems(tmp_path: Path) -> None:
    home = _build(
        tmp_path,
        ids=[i for i in BASE_IDS if i not in ("clean", "lint")],
        setup="Steps.\n",
        rules=_rules([a for a in AGENTS if a != "reviewer"]),
        readers=READERS.replace(
            "def check(part_root, settings, adopting):\n    return []\n", ""
        ),
    )
    report = _check(home)
    assert len(report.problems) == 5
    for text in ("clean", "lint", "For a feature", "reviewer", "check"):
        assert _mentions(report, text)
    assert report.ok is False


def test_static_needs_no_toolchain_or_fixture_content(tmp_path: Path) -> None:
    home = _build(tmp_path)
    (home / "fixture" / "a.fx").write_text("not valid anything \x00 {{{\n")
    assert _check(home).ok is True
