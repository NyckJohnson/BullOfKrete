"""Tests for the python_cli stack's `rules.md`, `setup.md` and `lint/ruff.toml`.

The guides are read through the stacks module (`rules`, `setup_guide`); only required facts and
headings are checked, never exact prose.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

import bull.Modules.stack_python_cli as pkg
from bull.Modules.stacks import docs
from bull.Modules.stacks.Contracts import Stack, StackError
from bull.Modules.stacks.registry import LiveStackRegistry

_FOLDER = Path(pkg.__file__).parent / "python_cli"

_BANNED = [
    "ios-pipeline",
    ".pipeline/",
    "config.sh",
    "stack.sh",
    "gates.sh",
    "ui-test-writer",
    "shellcheck",
    "xcode",
    "swift",
]


@pytest.fixture(scope="module")
def stack(tmp_path_factory: pytest.TempPathFactory) -> Stack:
    return LiveStackRegistry([], tmp_path_factory.mktemp("userdata")).load_path(_FOLDER)


def _headings(text: str) -> list[str]:
    return [
        m.group(1).strip().lower()
        for m in re.finditer(r"^## (.+)$", text, re.MULTILINE)
    ]


# --- rules.md -----------------------------------------------------------------------------


def test_rules_has_common_outline_and_one_section_per_agent(stack: Stack) -> None:
    headings = _headings((_FOLDER / "rules.md").read_text())
    assert "common" in headings
    assert "outline" in headings
    for agent in stack.manifest.agents:
        assert agent in headings


def test_rules_has_no_surveyor_section() -> None:
    assert "surveyor" not in _headings((_FOLDER / "rules.md").read_text())


def test_rules_for_surveyor_is_an_error(stack: Stack) -> None:
    with pytest.raises(StackError):
        docs.rules(stack, "surveyor")


def test_rules_for_each_agent_include_common_and_that_section(stack: Stack) -> None:
    for agent in stack.manifest.agents:
        text = docs.rules(stack, agent)
        headings = _headings(text)
        assert "common" in headings
        assert agent in headings


def test_rules_for_outline_is_only_the_outline_section(stack: Stack) -> None:
    headings = _headings(docs.rules(stack, "outline"))
    assert headings == ["outline"]


@pytest.mark.parametrize(
    "needle",
    [
        "Modules/<module>/Contracts/__init__.py",
        "mocks/__init__.py",
        "NotImplementedError",
        "tests/journey/",
        "# coverage-exempt",
        "# coverage-exempt-begin",
        "# coverage-exempt-end",
        'if __name__ == "__main__":',
        "BULL_URL_",
        "from __future__ import annotations",
        "mypy --strict",
        "pytest",
        "bull gates",
    ],
)
def test_rules_state_the_required_fact(needle: str) -> None:
    assert needle in (_FOLDER / "rules.md").read_text()


@pytest.mark.parametrize("word", _BANNED)
def test_rules_contain_no_other_stack_words(word: str) -> None:
    assert word not in (_FOLDER / "rules.md").read_text().lower()


def test_rules_contain_no_absolute_paths() -> None:
    assert "/Users/" not in (_FOLDER / "rules.md").read_text()


# --- setup.md -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "needle",
    [
        "uv",
        "pyproject.toml",
        "pytest-cov",
        "testpaths",
        "mypy_path",
        "hatchling",
        "bull config set package",
        "uv sync",
        "bull stack check",
    ],
)
def test_setup_states_the_required_step(needle: str) -> None:
    assert needle in (_FOLDER / "setup.md").read_text()


def test_setup_has_a_feature_section_mentioning_uv_add(stack: Stack) -> None:
    section = docs.setup_guide(stack, "For a feature")
    assert "uv add" in section


def test_setup_has_no_adoption_or_final_switch_section(stack: Stack) -> None:
    headings = _headings((_FOLDER / "setup.md").read_text())
    assert "for an adoption" not in headings
    assert "final switch" not in headings
    for section in ("For an adoption", "Final switch"):
        with pytest.raises(StackError):
            docs.setup_guide(stack, section)


@pytest.mark.parametrize("word", _BANNED)
def test_setup_contains_no_other_stack_words(word: str) -> None:
    assert word not in (_FOLDER / "setup.md").read_text().lower()


def test_setup_contains_no_absolute_paths() -> None:
    assert "/Users/" not in (_FOLDER / "setup.md").read_text()


# --- lint/ruff.toml -----------------------------------------------------------------------


def test_ruff_config_targets_py311_with_line_length_100() -> None:
    cfg = tomllib.loads((_FOLDER / "lint" / "ruff.toml").read_text())
    assert cfg["target-version"] == "py311"
    assert cfg["line-length"] == 100


def test_ruff_config_selects_exactly_the_agreed_rules_without_naming() -> None:
    cfg = tomllib.loads((_FOLDER / "lint" / "ruff.toml").read_text())
    selected = cfg["lint"]["select"]
    assert sorted(selected) == ["B", "E", "F", "I", "UP", "W"]
    assert "N" not in selected
