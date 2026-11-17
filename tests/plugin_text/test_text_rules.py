"""Text rules every plugin Markdown file must follow, checked over the real files."""

from __future__ import annotations

import re

import pytest

from bull.Modules.plugin_text.plugin_files import LivePluginText

AGENT_NAMES = [
    "code-writer",
    "coverage-analyst",
    "journey-test-writer",
    "legacy-test-scanner",
    "reviewer",
    "screen-builder",
    "skeleton-builder",
    "surveyor",
    "test-writer",
]
COMMAND_NAMES = [
    "adopt",
    "build",
    "discuss",
    "feature",
    "outline",
    "prototype",
    "resume",
    "setup",
    "skeleton",
    "stack",
    "status",
    "verify",
]
COMMAND_PATHS = [f"commands/{c}.md" for c in COMMAND_NAMES]
AGENT_PATHS = [f"agents/{a}.md" for a in AGENT_NAMES]
ALL_PATHS = ["orchestrator.md", *COMMAND_PATHS, *AGENT_PATHS]

# Top-level commands and subcommands, from the memo's Commands table.
TOP_LEVEL = {
    "init",
    "open",
    "doctor",
    "status",
    "feature",
    "adopt",
    "stack",
    "stacks",
    "gates",
    "coverage",
    "api",
    "part",
    "config",
    "migrate",
    "template",
    "hook",
    "statusline",
    "help",
}
SUBCOMMANDS = {
    "status": {
        "next",
        "stage",
        "checkpoint",
        "init-modules",
        "module",
        "unit",
        "attempt",
        "unblock",
        "pause",
        "resume",
        "wait",
        "approve",
        "refscan",
        "plan",
        "tick",
        "ref",
        "tags",
        "usage-check",
    },
    "feature": {
        "add",
        "import",
        "list",
        "move",
        "drop",
        "start",
        "plan",
        "accept",
        "abandon",
    },
    "adopt": {"start", "legacy", "finish", "abandon"},
    "stack": {"detect", "select", "rules", "setup", "check", "run", "install", "test"},
    "part": {"add", "list", "check"},
    "config": {"show", "set"},
    "template": {"outline", "backlog", "design"},
    "hook": {
        "session-start",
        "before-agent",
        "before-shell",
        "before-edit",
        "before-read",
        "agent-end",
    },
}
BANNED_WORDS = [
    "Xcode",
    "Swift",
    "SwiftUI",
    "UIKit",
    "iOS",
    "iPhone",
    "simulator",
    "XCUITest",
    "pytest",
    "mypy",
    "ruff",
    "xcodebuild",
]
V1_NAMES = [
    "ios-pipeline",
    ".pipeline/",
    "pipeline-resume",
    "pipeline-status",
    "ui-test-writer",
    "config.sh",
    "stack.sh",
    "gates.sh",
    "TaskCreate",
    "--app-ui-tests",
]


# --- helpers (the text rules themselves) -------------------------------------------------

_FENCE_LINE = re.compile(r"^[ \t]*(`{3,}|~{3,})(.*)$")
_SPAN = re.compile(r"`([^`\n]+)`")
_BULL_CMD = re.compile(r"(?<![\w./:-])bull[ \t]+([^\s`]+)(?:[ \t]+([^\s`]+))?")
_BARE_WORD = re.compile(r"^[a-z][a-z-]*$")
_BANNED = re.compile(
    r"\b(?:" + "|".join(map(re.escape, BANNED_WORDS)) + r")\b", re.IGNORECASE
)


def code_segments(text: str) -> list[str]:
    """Fenced block bodies and inline code spans (spans taken outside the fences).

    A fence line may be indented; it closes only on a fence of the same character, at
    least as long as the opening one, with nothing after it (as CommonMark).
    """
    segments: list[str] = []
    outside: list[str] = []
    body: list[str] = []
    opener: str | None = None
    for line in text.split("\n"):
        m = _FENCE_LINE.match(line.rstrip("\r"))
        if opener is None:
            if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
                opener = m.group(1)
                body = []
            else:
                outside.append(line)
        elif (
            m
            and m.group(1)[0] == opener[0]
            and len(m.group(1)) >= len(opener)
            and not m.group(2).strip()
        ):
            segments.append("\n".join(body))
            opener = None
        else:
            body.append(line)
    if opener is not None:
        segments.append("\n".join(body))
    segments.extend(m.group(1) for m in _SPAN.finditer("\n".join(outside)))
    return segments


def v1_names_in(text: str) -> list[str]:
    """v1 names found as whole names (`config.show` is not `config.sh`)."""
    return [
        n for n in V1_NAMES if re.search(r"(?<!\w)" + re.escape(n) + r"(?!\w)", text)
    ]


def _clean(token: str) -> str:
    return token.rstrip(",.;:)")


def bad_bull_commands(text: str) -> list[str]:
    """`bull <command>` snippets in code that are not in the Commands table."""
    bad: list[str] = []
    for segment in code_segments(text):
        for m in _BULL_CMD.finditer(segment):
            first = _clean(m.group(1))
            second = _clean(m.group(2)) if m.group(2) else None
            snippet = m.group(0).strip()
            if first.startswith(("-", "<")):
                continue
            if first not in TOP_LEVEL or (
                first in SUBCOMMANDS
                and second
                and _BARE_WORD.match(second)
                and second not in SUBCOMMANDS[first]
            ):
                bad.append(snippet)
    return bad


def bad_command_refs(text: str, command_names: list[str]) -> list[str]:
    return [
        m.group(0)
        for m in re.finditer(r"/bull:([a-z][a-z-]*)", text)
        if m.group(1) not in command_names
    ]


def bad_model_refs(text: str, agent_names: list[str]) -> list[str]:
    return [
        m.group(0)
        for m in re.finditer(r"\bmodels\.([a-z][a-z-]*)", text)
        if m.group(1) not in agent_names
    ]


def banned_words_in(text: str) -> list[str]:
    return [m.group(0) for m in _BANNED.finditer(text)]


def frontmatter(text: str) -> dict[str, str] | None:
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return None
    out: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return out
        if ":" in line:
            key, _, value = line.partition(":")
            out[key.strip()] = value.strip()
    return None


_TEXTS: dict[str, str] = {}


def real_text(path: str) -> str:
    if not _TEXTS:
        _TEXTS.update({f.path: f.text for f in LivePluginText().files()})
    return _TEXTS[path]


# --- the helpers on small inline strings -------------------------------------------------


def test_banned_word_inside_another_word_is_allowed() -> None:
    assert banned_words_in("a swiftly rubyist iosphere pytester") == []


@pytest.mark.parametrize("word", BANNED_WORDS)
def test_banned_word_as_a_whole_word_is_found_in_any_case(word: str) -> None:
    assert banned_words_in(f"use {word.upper()} here") == [word.upper()]
    assert banned_words_in(f"{word.lower()}.") == [word.lower()]


@pytest.mark.parametrize(
    "text",
    [
        "Run `bull status next`.",
        "Run `bull status`.",
        "Run `bull status --json`.",
        "Run `bull --version`.",
        "Run `bull gates <M> --fast`.",
        "Run `bull <command>`.",
        "Run `bull status <sub>`.",
        "Run `bull <command> <sub>`.",
        'Run `bull feature add "T: d"`.',
        "Run `bull status ref tag <x>`.",
        "Run `git tag $(bull status ref tag <name>)`.",
        "```\nbull stack check\nbull part list\n```",
        "Use `bull config set models.reviewer sonnet`.",
    ],
)
def test_known_bull_commands_pass(text: str) -> None:
    assert bad_bull_commands(text) == []


@pytest.mark.parametrize(
    "text",
    [
        "Run `bull frobnicate`.",
        "Run `bull status frobnicate`.",
        "Run `bull feature nope x`.",
        "```\nbull frobnicate now\n```",
    ],
)
def test_unknown_bull_commands_fail(text: str) -> None:
    assert bad_bull_commands(text) != []


def test_indented_fence_lines_count_as_a_fenced_block() -> None:
    assert bad_bull_commands("- item\n\n  ```\n  bull frobnicate now\n  ```\n") != []


def test_four_backtick_block_holding_a_three_backtick_example_is_one_block() -> None:
    text = "````\nbull status next\n```\nbull frobnicate\n```\nbull part list\n````\n"
    assert code_segments(text) == [
        "bull status next\n```\nbull frobnicate\n```\nbull part list"
    ]
    assert bad_bull_commands(text) != []


def test_prose_after_a_longer_fence_is_not_treated_as_code() -> None:
    text = "````\nbull status next\n```\nstill code\n````\nThen bull frobnicate the thing.\n"
    assert bad_bull_commands(text) == []
    assert "Then bull frobnicate the thing." not in " ".join(code_segments(text))


def test_fence_does_not_close_on_a_different_character_or_shorter_run() -> None:
    text = "```\nbull status next\n~~~\n``\nbull frobnicate\n```\nafter\n"
    assert code_segments(text) == ["bull status next\n~~~\n``\nbull frobnicate"]


def test_tilde_fence_closes_on_tildes() -> None:
    assert code_segments("~~~\nbull part list\n~~~\nprose\n") == ["bull part list"]


def test_v1_file_name_matches_whole_names_only() -> None:
    assert v1_names_in("see `config.show` for it") == []
    assert v1_names_in("edit config.sh now") == ["config.sh"]
    assert v1_names_in("edit config.sh.") == ["config.sh"]


def test_bull_command_outside_backticks_is_not_checked() -> None:
    assert bad_bull_commands("Then bull frobnicate the thing, and bull is great.") == []


def test_bull_in_a_slash_command_or_path_is_not_a_command() -> None:
    assert bad_bull_commands("`/bull:status` and `.bull/status.json`") == []


def test_command_reference_matching_a_command_file_passes() -> None:
    assert bad_command_refs("Run /bull:status then /bull:build.", COMMAND_NAMES) == []


def test_command_reference_without_a_command_file_fails() -> None:
    assert bad_command_refs("Run /bull:nope.", COMMAND_NAMES) == ["/bull:nope"]


def test_placeholder_command_reference_is_not_checked() -> None:
    assert bad_command_refs("Use /bull:<name>.", COMMAND_NAMES) == []


def test_model_reference_matching_an_agent_passes() -> None:
    assert (
        bad_model_refs("Set models.reviewer or models.test-writer.", AGENT_NAMES) == []
    )


def test_model_reference_without_an_agent_fails() -> None:
    assert bad_model_refs("Set models.nobody.", AGENT_NAMES) == ["models.nobody"]


def test_placeholder_model_reference_is_not_checked() -> None:
    assert bad_model_refs("Set `models.<agent>`.", AGENT_NAMES) == []


# --- the text rules over every real file -------------------------------------------------


def test_every_real_plugin_file_is_covered_by_these_rules() -> None:
    assert sorted(f.path for f in LivePluginText().files()) == sorted(ALL_PATHS)


@pytest.mark.parametrize("path", COMMAND_PATHS)
def test_command_file_has_frontmatter_with_description(path: str) -> None:
    fm = frontmatter(real_text(path))
    assert fm is not None
    assert fm.get("description")


@pytest.mark.parametrize("path", AGENT_PATHS)
def test_agent_file_has_name_description_and_tools(path: str) -> None:
    fm = frontmatter(real_text(path))
    assert fm is not None
    assert fm.get("name", "").strip("\"'") == path.removeprefix("agents/").removesuffix(
        ".md"
    )
    assert fm.get("description")
    assert fm.get("tools")


@pytest.mark.parametrize("path", AGENT_PATHS)
def test_agent_frontmatter_has_no_model_line(path: str) -> None:
    fm = frontmatter(real_text(path))
    assert fm is not None
    assert "model" not in fm


@pytest.mark.parametrize("path", ALL_PATHS)
def test_slash_command_references_match_a_command_file(path: str) -> None:
    assert bad_command_refs(real_text(path), COMMAND_NAMES) == []


@pytest.mark.parametrize("path", ALL_PATHS)
def test_model_setting_references_match_an_agent(path: str) -> None:
    assert bad_model_refs(real_text(path), AGENT_NAMES) == []


@pytest.mark.parametrize("path", ALL_PATHS)
def test_bull_commands_in_code_match_the_commands_table(path: str) -> None:
    assert bad_bull_commands(real_text(path)) == []


@pytest.mark.parametrize("path", ALL_PATHS)
def test_no_v1_names_appear(path: str) -> None:
    text = real_text(path)
    assert v1_names_in(text) == []


@pytest.mark.parametrize("path", ALL_PATHS)
def test_no_banned_language_toolchain_or_platform_words_appear(path: str) -> None:
    assert banned_words_in(real_text(path)) == []
