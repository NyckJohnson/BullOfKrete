"""Tests for `bull.Modules.plugin_text.plugin_files` (LivePluginText)."""

from __future__ import annotations

from pathlib import Path

import pytest

from bull.Modules.foundation.Contracts import BullError
from bull.Modules.plugin_text.Contracts import AgentDoc, PluginFile
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
REAL_PATHS = sorted(
    ["orchestrator.md"]
    + [f"commands/{c}.md" for c in COMMAND_NAMES]
    + [f"agents/{a}.md" for a in AGENT_NAMES]
)


def agent_text(
    name: str, description: str = "Does a job.", tools: str = "Read, Grep"
) -> str:
    return (
        f"---\nname: {name}\ndescription: {description}\ntools: {tools}\n---\nBody.\n"
    )


def make_plugin(
    root: Path,
    agents: dict[str, str] | None = None,
    commands: dict[str, str] | None = None,
    orchestrator: str | None = "# orchestrator\n",
) -> Path:
    (root / "agents").mkdir(parents=True, exist_ok=True)
    (root / "commands").mkdir(parents=True, exist_ok=True)
    if orchestrator is not None:
        (root / "orchestrator.md").write_bytes(orchestrator.encode("utf-8"))
    for name, text in (agents or {}).items():
        (root / "agents" / f"{name}.md").write_bytes(text.encode("utf-8"))
    for name, text in (commands or {}).items():
        (root / "commands" / f"{name}.md").write_bytes(text.encode("utf-8"))
    return root


# --- files() -----------------------------------------------------------------------------


def test_files_lists_orchestrator_commands_and_agents_sorted(tmp_path: Path) -> None:
    make_plugin(
        tmp_path,
        agents={
            "reviewer": agent_text("reviewer"),
            "code-writer": agent_text("code-writer"),
        },
        commands={
            "status": "---\ndescription: x\n---\n",
            "build": "---\ndescription: y\n---\n",
        },
    )
    paths = [f.path for f in LivePluginText(tmp_path).files()]
    assert paths == [
        "agents/code-writer.md",
        "agents/reviewer.md",
        "commands/build.md",
        "commands/status.md",
        "orchestrator.md",
    ]


def test_files_ignores_python_files_and_other_folders(tmp_path: Path) -> None:
    make_plugin(tmp_path, agents={"reviewer": agent_text("reviewer")})
    (tmp_path / "plugin_files.py").write_text("x = 1\n")
    (tmp_path / "agents" / "helper.py").write_text("x = 1\n")
    (tmp_path / "commands" / "notes.txt").write_text("not markdown\n")
    (tmp_path / "other").mkdir()
    (tmp_path / "other" / "extra.md").write_text("# extra\n")
    (tmp_path / "README.md").write_text("# readme\n")
    paths = [f.path for f in LivePluginText(tmp_path).files()]
    assert paths == ["agents/reviewer.md", "orchestrator.md"]


def test_files_paths_are_posix_relative_to_root(tmp_path: Path) -> None:
    make_plugin(tmp_path, commands={"build": "---\ndescription: y\n---\n"})
    for f in LivePluginText(tmp_path).files():
        assert not f.path.startswith("/")
        assert "\\" not in f.path
        assert (tmp_path / f.path).is_file()


def test_files_reads_text_as_utf8(tmp_path: Path) -> None:
    text = "---\ndescription: café — ✅\n---\nBody ❌\n"
    make_plugin(tmp_path, commands={"build": text}, orchestrator="# über ✋\n")
    by_path = {f.path: f for f in LivePluginText(tmp_path).files()}
    assert by_path["commands/build.md"] == PluginFile("commands/build.md", text)
    assert by_path["orchestrator.md"].text == "# über ✋\n"


def test_files_returns_plugin_file_values(tmp_path: Path) -> None:
    make_plugin(tmp_path, orchestrator="# o\n")
    assert LivePluginText(tmp_path).files() == [PluginFile("orchestrator.md", "# o\n")]


def test_files_missing_orchestrator_raises_bull_error_naming_it(tmp_path: Path) -> None:
    make_plugin(
        tmp_path, agents={"reviewer": agent_text("reviewer")}, orchestrator=None
    )
    with pytest.raises(BullError) as exc:
        LivePluginText(tmp_path).files()
    assert "orchestrator.md" in exc.value.message


@pytest.mark.parametrize("folder", ["agents", "commands"])
def test_files_non_utf8_file_raises_bull_error_naming_its_path(
    tmp_path: Path, folder: str
) -> None:
    make_plugin(tmp_path)
    (tmp_path / folder / "broken.md").write_bytes(b"\xff\xfe")
    with pytest.raises(BullError) as exc:
        LivePluginText(tmp_path).files()
    assert f"{folder}/broken.md" in exc.value.message


def test_files_returns_crlf_line_endings_unchanged(tmp_path: Path) -> None:
    text = "---\r\ndescription: d\r\n---\r\nBody\r\n"
    make_plugin(tmp_path, commands={"build": text}, orchestrator="# o\r\n\r\n")
    by_path = {f.path: f.text for f in LivePluginText(tmp_path).files()}
    assert by_path["commands/build.md"] == text
    assert by_path["orchestrator.md"] == "# o\r\n\r\n"


# --- orchestrator() ----------------------------------------------------------------------


def test_orchestrator_returns_orchestrator_text(tmp_path: Path) -> None:
    make_plugin(tmp_path, orchestrator="# bull — orchestrator instructions\n\nRules.\n")
    assert (
        LivePluginText(tmp_path).orchestrator()
        == "# bull — orchestrator instructions\n\nRules.\n"
    )


def test_orchestrator_missing_file_raises_bull_error_naming_it(tmp_path: Path) -> None:
    make_plugin(tmp_path, orchestrator=None)
    with pytest.raises(BullError) as exc:
        LivePluginText(tmp_path).orchestrator()
    assert "orchestrator.md" in exc.value.message


# --- agents() ----------------------------------------------------------------------------


def test_agents_parses_unquoted_values(tmp_path: Path) -> None:
    make_plugin(
        tmp_path, agents={"reviewer": agent_text("reviewer", "Reviews a unit.", "Read")}
    )
    assert LivePluginText(tmp_path).agents() == [
        AgentDoc("reviewer", "Reviews a unit.", ("Read",), "models.reviewer")
    ]


def test_agents_strips_one_pair_of_double_or_single_quotes(tmp_path: Path) -> None:
    make_plugin(
        tmp_path,
        agents={
            "a-one": '---\nname: "a-one"\ndescription: "Quoted: yes."\ntools: "Read, Edit"\n---\n',
            "b-two": "---\nname: 'b-two'\ndescription: 'Single quoted.'\ntools: Read\n---\n",
        },
    )
    docs = LivePluginText(tmp_path).agents()
    assert docs == [
        AgentDoc("a-one", "Quoted: yes.", ("Read", "Edit"), "models.a-one"),
        AgentDoc("b-two", "Single quoted.", ("Read",), "models.b-two"),
    ]


def test_agents_strips_only_one_pair_of_quotes(tmp_path: Path) -> None:
    make_plugin(
        tmp_path,
        agents={"x": "---\nname: x\ndescription: \"'inner'\"\ntools: Read\n---\n"},
    )
    assert LivePluginText(tmp_path).agents()[0].description == "'inner'"


def test_agents_description_keeps_colons_after_the_first(tmp_path: Path) -> None:
    make_plugin(
        tmp_path,
        agents={"x": "---\nname: x\ndescription: Stage 1: discuss\ntools: Read\n---\n"},
    )
    assert LivePluginText(tmp_path).agents()[0].description == "Stage 1: discuss"


def test_agents_trims_whitespace_around_values(tmp_path: Path) -> None:
    make_plugin(
        tmp_path,
        agents={
            "x": "---\nname:   x  \ndescription:    Spaced out.   \ntools: Read\n---\n"
        },
    )
    doc = LivePluginText(tmp_path).agents()[0]
    assert doc.name == "x"
    assert doc.description == "Spaced out."


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Read, Grep, Glob", ("Read", "Grep", "Glob")),
        ("Read,Grep", ("Read", "Grep")),
        ("  Read  ,   Grep  ", ("Read", "Grep")),
        ("Read, , Grep,", ("Read", "Grep")),
        (",Read,,", ("Read",)),
        ("Read", ("Read",)),
    ],
)
def test_agents_splits_tools_on_commas_trimming_and_dropping_empty(
    tmp_path: Path, raw: str, expected: tuple[str, ...]
) -> None:
    make_plugin(tmp_path, agents={"x": agent_text("x", tools=raw)})
    assert LivePluginText(tmp_path).agents()[0].tools == expected


def test_agents_returns_one_doc_per_agent_file_in_path_order(tmp_path: Path) -> None:
    make_plugin(
        tmp_path,
        agents={
            "surveyor": agent_text("surveyor"),
            "code-writer": agent_text("code-writer"),
            "reviewer": agent_text("reviewer"),
        },
        commands={"build": "---\ndescription: y\n---\n"},
    )
    docs = LivePluginText(tmp_path).agents()
    assert [d.name for d in docs] == ["code-writer", "reviewer", "surveyor"]
    assert [d.model_setting for d in docs] == [
        "models.code-writer",
        "models.reviewer",
        "models.surveyor",
    ]


def test_agents_is_empty_when_there_are_no_agent_files(tmp_path: Path) -> None:
    make_plugin(tmp_path)
    assert LivePluginText(tmp_path).agents() == []


def test_agents_file_without_frontmatter_raises_naming_the_file(tmp_path: Path) -> None:
    make_plugin(tmp_path, agents={"reviewer": "Just a body, no frontmatter.\n"})
    with pytest.raises(BullError) as exc:
        LivePluginText(tmp_path).agents()
    assert "agents/reviewer.md" in exc.value.message


def test_agents_unclosed_frontmatter_counts_as_missing(tmp_path: Path) -> None:
    text = "---\nname: reviewer\ndescription: d\ntools: Read\nBody never closed.\n"
    make_plugin(tmp_path, agents={"reviewer": text})
    with pytest.raises(BullError) as exc:
        LivePluginText(tmp_path).agents()
    assert "agents/reviewer.md" in exc.value.message


def test_agents_frontmatter_not_on_first_line_counts_as_missing(tmp_path: Path) -> None:
    text = "\n---\nname: reviewer\ndescription: d\ntools: Read\n---\n"
    make_plugin(tmp_path, agents={"reviewer": text})
    with pytest.raises(BullError) as exc:
        LivePluginText(tmp_path).agents()
    assert "agents/reviewer.md" in exc.value.message


@pytest.mark.parametrize("missing", ["name", "description", "tools"])
def test_agents_missing_key_raises_naming_file_and_key(
    tmp_path: Path, missing: str
) -> None:
    lines = {
        "name": "name: reviewer",
        "description": "description: d",
        "tools": "tools: Read",
    }
    del lines[missing]
    text = "---\n" + "\n".join(lines.values()) + "\n---\nBody\n"
    make_plugin(tmp_path, agents={"reviewer": text})
    with pytest.raises(BullError) as exc:
        LivePluginText(tmp_path).agents()
    assert "agents/reviewer.md" in exc.value.message
    assert missing in exc.value.message


def test_agents_name_differing_from_file_name_raises_naming_file(
    tmp_path: Path,
) -> None:
    make_plugin(tmp_path, agents={"reviewer": agent_text("other-name")})
    with pytest.raises(BullError) as exc:
        LivePluginText(tmp_path).agents()
    assert "agents/reviewer.md" in exc.value.message


def test_agents_error_names_the_bad_file_among_good_ones(tmp_path: Path) -> None:
    make_plugin(
        tmp_path,
        agents={
            "code-writer": agent_text("code-writer"),
            "reviewer": "no frontmatter\n",
        },
    )
    with pytest.raises(BullError) as exc:
        LivePluginText(tmp_path).agents()
    assert "agents/reviewer.md" in exc.value.message


# --- the real module folder --------------------------------------------------------------


def test_real_files_are_exactly_the_memo_files_line() -> None:
    assert [f.path for f in LivePluginText().files()] == REAL_PATHS


def test_real_files_count_is_one_orchestrator_twelve_commands_nine_agents() -> None:
    paths = [f.path for f in LivePluginText().files()]
    assert paths.count("orchestrator.md") == 1
    assert sum(p.startswith("commands/") for p in paths) == 12
    assert sum(p.startswith("agents/") for p in paths) == 9


def test_real_orchestrator_matches_the_orchestrator_file_entry() -> None:
    live = LivePluginText()
    entry = next(f for f in live.files() if f.path == "orchestrator.md")
    assert live.orchestrator() == entry.text


def test_real_agents_are_exactly_the_nine_agents() -> None:
    docs = LivePluginText().agents()
    assert [d.name for d in docs] == AGENT_NAMES
    assert [d.model_setting for d in docs] == [f"models.{n}" for n in AGENT_NAMES]


@pytest.mark.parametrize("name", AGENT_NAMES)
def test_real_agent_has_description_and_tools(name: str) -> None:
    doc = next(d for d in LivePluginText().agents() if d.name == name)
    assert doc.description.strip()
    assert doc.tools
    assert all(t.strip() for t in doc.tools)
