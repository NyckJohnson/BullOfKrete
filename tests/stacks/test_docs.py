"""Tests for `bull.Modules.stacks.docs`.

Shapes chosen here (for the code-writer):
  - `rules(stack: Stack, agent: str) -> str`: reads `<stack.home>/rules.md`.
  - `setup_guide(stack: Stack, section: str | None = None) -> str`: reads `setup.md`.
  - Sections are `## ` headings; text of a section is everything up to the next `## `.
  - Section selection is by heading text; an unknown section or agent raises StackError.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bull.Modules.stacks.Contracts import Stack, StackError
from bull.Modules.stacks.docs import rules, setup_guide

from .fakes import registry_with, stack_of

RULES = """# Sample rules

## common
- COMMON-LINE

## Test-Writer
- TESTWRITER-LINE

## reviewer
- REVIEWER-LINE

## outline
- OUTLINE-LINE
"""

SETUP = """# Setup

1. STEP-ONE
2. STEP-TWO

## For a feature
- FEATURE-LINE

## Final switch
- SWITCH-LINE
"""


def make(tmp_path: Path, rules_text: str = RULES, setup_text: str = SETUP) -> Stack:
    (tmp_path / "rules.md").write_text(rules_text, encoding="utf-8")
    (tmp_path / "setup.md").write_text(setup_text, encoding="utf-8")
    return stack_of(registry_with(tmp_path))


def test_rules_returns_common_plus_the_agents_section(tmp_path: Path) -> None:
    text = rules(make(tmp_path), "reviewer")
    assert "COMMON-LINE" in text
    assert "REVIEWER-LINE" in text
    assert "TESTWRITER-LINE" not in text
    assert "OUTLINE-LINE" not in text


def test_rules_puts_common_before_the_agent_section(tmp_path: Path) -> None:
    text = rules(make(tmp_path), "reviewer")
    assert text.index("COMMON-LINE") < text.index("REVIEWER-LINE")


def test_rules_matches_the_heading_case_insensitively(tmp_path: Path) -> None:
    text = rules(make(tmp_path), "test-writer")
    assert "TESTWRITER-LINE" in text


def test_rules_matches_a_differently_cased_agent_name(tmp_path: Path) -> None:
    text = rules(make(tmp_path), "REVIEWER")
    assert "REVIEWER-LINE" in text


def test_rules_matches_a_differently_cased_common_heading(tmp_path: Path) -> None:
    text = rules(make(tmp_path, RULES.replace("## common", "## COMMON")), "reviewer")
    assert "COMMON-LINE" in text


def test_rules_for_outline_is_only_the_outline_section(tmp_path: Path) -> None:
    text = rules(make(tmp_path), "outline")
    assert "OUTLINE-LINE" in text
    assert "COMMON-LINE" not in text
    assert "REVIEWER-LINE" not in text


def test_rules_for_an_agent_missing_from_the_file_raises(tmp_path: Path) -> None:
    with pytest.raises(StackError) as caught:
        rules(make(tmp_path), "code-writer")
    assert "code-writer" in f"{caught.value.message} {caught.value.fix}"


def test_rules_for_an_empty_agent_name_raises(tmp_path: Path) -> None:
    with pytest.raises(StackError):
        rules(make(tmp_path), "")


def test_setup_guide_without_a_section_is_the_whole_file(tmp_path: Path) -> None:
    assert setup_guide(make(tmp_path)) == SETUP


def test_setup_guide_with_a_section_returns_only_that_section(tmp_path: Path) -> None:
    text = setup_guide(make(tmp_path), "For a feature")
    assert "FEATURE-LINE" in text
    assert "STEP-ONE" not in text
    assert "SWITCH-LINE" not in text


def test_setup_guide_returns_the_last_section_to_the_end(tmp_path: Path) -> None:
    text = setup_guide(make(tmp_path), "Final switch")
    assert "SWITCH-LINE" in text
    assert "FEATURE-LINE" not in text


def test_setup_guide_with_an_unknown_section_raises(tmp_path: Path) -> None:
    with pytest.raises(StackError) as caught:
        setup_guide(make(tmp_path), "For an adoption")
    assert "For an adoption" in f"{caught.value.message} {caught.value.fix}"


FENCED_RULES = """## common
- COMMON-LINE

## reviewer
- REVIEWER-LINE
```
## code-writer
- IN-FENCE-LINE
```
- AFTER-FENCE-LINE

## outline
- OUTLINE-LINE
"""

FENCED_SETUP = """## Real
- REAL-LINE
```
## Fake
- FAKE-LINE
```
- AFTER-FENCE-LINE

## Next
- NEXT-LINE
"""


def test_rules_does_not_treat_a_heading_inside_a_code_fence_as_a_section(
    tmp_path: Path,
) -> None:
    stack = make(tmp_path, FENCED_RULES)
    text = rules(stack, "reviewer")
    assert "IN-FENCE-LINE" in text
    assert "AFTER-FENCE-LINE" in text
    assert "OUTLINE-LINE" not in text
    with pytest.raises(StackError):
        rules(stack, "code-writer")


def test_setup_guide_does_not_treat_a_heading_inside_a_code_fence_as_a_section(
    tmp_path: Path,
) -> None:
    stack = make(tmp_path, setup_text=FENCED_SETUP)
    text = setup_guide(stack, "Real")
    assert "FAKE-LINE" in text
    assert "AFTER-FENCE-LINE" in text
    assert "NEXT-LINE" not in text
    with pytest.raises(StackError):
        setup_guide(stack, "Fake")
