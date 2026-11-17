"""Content of agents/reviewer.md, coverage-analyst.md and journey-test-writer.md."""

from __future__ import annotations

import re

import pytest

from bull.Modules.plugin_text.plugin_files import LivePluginText

AGENTS = ("reviewer", "coverage-analyst", "journey-test-writer")

DESCRIPTIONS = {
    "reviewer": (
        "Stage 5 and 6. Read-only targeted review of one work unit's files, one category, "
        "the whole app, a feature, a switch-over or a stack. Also confirms coverage "
        "exemptions."
    ),
    "coverage-analyst": (
        "Stage 5. Explains why each uncovered block of a module is uncovered and "
        "classifies it as missed, exempt or not-in-spec."
    ),
    "journey-test-writer": (
        "Stage 6. Writes one end-to-end journey test per user journey in the memo and "
        "runs them."
    ),
}

TOOLS = {
    "reviewer": ("Read", "Grep", "Glob", "Bash"),
    "coverage-analyst": ("Read", "Grep", "Glob", "Bash", "Edit"),
    "journey-test-writer": ("Read", "Write", "Edit", "Grep", "Glob", "Bash"),
}


def _norm(text: str) -> str:
    """Lower-case, backticks dropped, whitespace collapsed."""
    return re.sub(r"\s+", " ", text.replace("`", "")).strip().lower()


def _raw(name: str) -> str:
    path = f"agents/{name}.md"
    for f in LivePluginText().files():
        if f.path == path:
            return f.text
    raise AssertionError(f"no file {path}")


def _frontmatter(name: str) -> dict[str, str]:
    lines = _raw(name).split("\n")
    assert lines and lines[0].strip() == "---", "no frontmatter"
    out: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return out
        m = re.match(r"^([\w-]+):[ \t]*(.*)$", line)
        if m:
            value = m.group(2).strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            out[m.group(1)] = value
    raise AssertionError("frontmatter never closed")


def _body(name: str) -> str:
    parts = _raw(name).split("\n---", 1)
    return parts[1] if len(parts) == 2 else _raw(name)


def has_all(name: str, *terms: str) -> None:
    norm = _norm(_body(name))
    missing = [t for t in terms if t.lower() not in norm]
    assert not missing, f"{name}: missing {missing}"


def has_any(name: str, *terms: str) -> None:
    norm = _norm(_body(name))
    assert any(t.lower() in norm for t in terms), f"{name}: none of {terms}"


def in_order(name: str, *terms: str) -> None:
    norm = _norm(_body(name))
    pos = 0
    for t in terms:
        found = norm.find(t.lower(), pos)
        assert found >= 0, f"{name}: {t!r} missing or out of order (after {pos})"
        pos = found + len(t)


def after(name: str, marker: str, *terms: str) -> None:
    """Every term appears in the text following the first `marker`."""
    norm = _norm(_body(name))
    idx = norm.find(marker.lower())
    assert idx >= 0, f"{name}: no {marker!r}"
    tail = norm[idx + len(marker) :]
    missing = [t for t in terms if t.lower() not in tail]
    assert not missing, f"{name}: after {marker!r} missing {missing}"


def _fences(name: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] | None = None
    for line in _body(name).split("\n"):
        if line.strip().startswith("```"):
            if current is None:
                current = []
            else:
                blocks.append("\n".join(current))
                current = None
        elif current is not None:
            current.append(line)
    return blocks


def _report_block(name: str) -> str:
    for block in _fences(name):
        first = next((ln for ln in block.split("\n") if ln.strip()), "")
        if first.strip().startswith("STATUS:"):
            return block
    raise AssertionError(f"{name}: no fenced report block starting with STATUS:")


def _section(name: str, heading: str) -> str:
    """Text of the `## <heading>` section (up to the next `## `)."""
    m = re.search(
        rf"^##[ \t]+{re.escape(heading)}[ \t]*$(.*?)(?=^##[ \t]|\Z)",
        _body(name),
        re.DOTALL | re.MULTILINE | re.IGNORECASE,
    )
    assert m, f"{name}: no section {heading!r}"
    return m.group(1)


# --- every agent -------------------------------------------------------------------------


@pytest.mark.parametrize("name", AGENTS)
def test_frontmatter_name_is_the_file_name(name: str) -> None:
    assert _frontmatter(name)["name"] == name


@pytest.mark.parametrize("name", AGENTS)
def test_description_matches_the_note(name: str) -> None:
    assert _norm(_frontmatter(name)["description"]).startswith(
        _norm(DESCRIPTIONS[name])
    )


@pytest.mark.parametrize("name", AGENTS)
def test_tools_are_exactly_the_notes_list(name: str) -> None:
    doc = next(a for a in LivePluginText().agents() if a.name == name)
    assert doc.tools == TOOLS[name]


@pytest.mark.parametrize("name", AGENTS)
def test_tools_line_has_no_agent_tool(name: str) -> None:
    tools = [t.strip() for t in _frontmatter(name)["tools"].split(",")]
    assert "Agent" not in tools


@pytest.mark.parametrize("name", AGENTS)
def test_no_model_line_in_frontmatter(name: str) -> None:
    assert "model" not in _frontmatter(name)
    head = _raw(name).split("\n---", 1)[0]
    assert not re.search(r"^model:", head, re.MULTILINE)


@pytest.mark.parametrize("name", AGENTS)
def test_stack_rules_section_names_the_command_and_part_flag(name: str) -> None:
    section = _norm(_section(name, "Stack rules"))
    assert f"bull stack rules {name}" in section
    assert "--part" in section


@pytest.mark.parametrize("name", AGENTS)
def test_report_block_is_fenced_and_starts_with_status(name: str) -> None:
    assert "done" in _report_block(name)


def test_journey_test_writer_question_block_has_its_four_lines() -> None:
    text = _body("journey-test-writer")
    for field in ("ASK:", "WHY:", "OPTIONS:", "RECOMMEND:"):
        assert field in text, f"no {field}"


def test_journey_test_writer_question_says_the_human_sees_none_of_your_files() -> None:
    has_all("journey-test-writer", "the human sees none of your files")


@pytest.mark.parametrize("name", ("reviewer", "coverage-analyst"))
def test_checker_report_is_status_done_without_blocked(name: str) -> None:
    block = _report_block(name)
    assert "STATUS: done" in block
    assert "blocked" not in block.lower()


# --- reviewer ----------------------------------------------------------------------------


def test_reviewer_never_modifies_files() -> None:
    has_any("reviewer", "never modify", "do not modify", "never modifies")


def test_reviewer_takes_scope_and_categories_from_the_brief() -> None:
    has_all("reviewer", "SCOPE", "CATEGORIES")


@pytest.mark.parametrize(
    "term",
    [
        "correctness",
        "error handling",
        "security",
        "concurrency",
        "spec and api design",
    ],
)
def test_reviewer_has_each_of_the_five_categories(term: str) -> None:
    has_all("reviewer", term)


def test_reviewer_security_names_secure_storage_and_encrypted_transport() -> None:
    has_all("reviewer", "secure storage", "https")


def test_reviewer_concurrency_names_reference_cycles() -> None:
    has_all("reviewer", "reference cycles")


def test_reviewer_concurrency_puts_ui_work_where_the_stack_rules_say() -> None:
    has_all("reviewer", "where the stack rules say")


@pytest.mark.parametrize("word", ["Dynamic Type", "dark mode", "retain"])
def test_reviewer_uses_neutral_wording(word: str) -> None:
    assert word.lower() not in _norm(_raw("reviewer"))


def test_reviewer_scope_unit_files() -> None:
    has_any("reviewer", "unit's files", "unit files", "files of the unit")


def test_reviewer_scope_whole_app() -> None:
    has_all("reviewer", "SCOPE: whole app", "consistency")


def test_reviewer_scope_feature_uses_git_diff_against_trunk() -> None:
    has_all("reviewer", "SCOPE: feature <slug>", "git diff")
    has_any("reviewer", "bull status ref trunk", "trunk")


def test_reviewer_scope_feature_finds_no_leftover_markers() -> None:
    has_all("reviewer", "(feature <slug>)", "signature updated (feature <slug>)")


def test_reviewer_change_brief_checks_unchanged_behaviors_keep_tests() -> None:
    has_all("reviewer", "CHANGE: <slug>")


def test_reviewer_scope_switch_over() -> None:
    has_all("reviewer", "SCOPE: switch-over <M>")


def test_reviewer_switch_over_checks_callers_and_removed_legacy_code() -> None:
    after("reviewer", "scope: switch-over <m>", "contracts", "legacy")


def test_reviewer_legacy_types_in_module_code_are_a_blocker_during_adoption() -> None:
    has_all("reviewer", "legacy types", "adoption", "blocker")


def test_reviewer_checks_coverage_exemption_reasons() -> None:
    has_all("reviewer", "coverage-exempt", "reason")


def test_reviewer_checks_exempt_files_have_no_executable_code() -> None:
    has_all("reviewer", "coverage-exempt-file", "executable")


def test_reviewer_checks_interfaces_match_in_meaning() -> None:
    has_all("reviewer", "interface")


def test_reviewer_severity_has_blocker_and_minor() -> None:
    has_all("reviewer", "blocker", "minor")


def test_reviewer_result_fail_only_with_a_blocker() -> None:
    has_all("reviewer", "RESULT: fail")
    has_any("reviewer", "only with at least one blocker", "only if there is a blocker")


def test_reviewer_report_block_has_result_and_findings() -> None:
    block = _report_block("reviewer")
    for field in ("RESULT:", "FINDINGS:"):
        assert field in block


def test_reviewer_scope_stack_checks_against_design_and_stack_files() -> None:
    has_all("reviewer", "SCOPE: stack", "DESIGN.md", "Stack files")


def test_reviewer_scope_stack_checks_honest_readers_and_portability() -> None:
    has_all("reviewer", "no tests ran", "author's machine")


# --- coverage-analyst --------------------------------------------------------------------


@pytest.mark.parametrize("cls", ["missed", "exempt", "not-in-spec"])
def test_coverage_analyst_names_each_class(cls: str) -> None:
    has_all("coverage-analyst", cls)


def test_coverage_analyst_missed_names_the_spec_behavior_and_writes_no_tests() -> None:
    has_all("coverage-analyst", "spec behavior")
    has_any("coverage-analyst", "write no tests", "do not write tests", "no tests")


def test_coverage_analyst_exempt_adds_the_marker_and_edits_nothing_else() -> None:
    has_all("coverage-analyst", "marker", "nothing else")


def test_coverage_analyst_not_in_spec_is_described_and_unchanged() -> None:
    has_all("coverage-analyst", "not-in-spec", "one line")
    has_any("coverage-analyst", "change nothing", "do not change", "unchanged")


@pytest.mark.parametrize(
    "syntax",
    [
        "coverage-exempt:",
        "coverage-exempt-begin:",
        "coverage-exempt-end",
        "coverage-exempt-file:",
    ],
)
def test_coverage_analyst_shows_each_marker_syntax(syntax: str) -> None:
    has_all("coverage-analyst", syntax)


def test_coverage_analyst_file_marker_goes_in_the_first_10_lines() -> None:
    has_all("coverage-analyst", "first 10 lines")


def test_coverage_analyst_marker_syntax_follows_the_stack_rules() -> None:
    has_all("coverage-analyst", "stack rules")


def test_coverage_analyst_files_without_coverage_data() -> None:
    has_all("coverage-analyst", "without coverage data")


def test_coverage_analyst_declaration_only_file_is_exempt_with_file_marker() -> None:
    has_all("coverage-analyst", "declarations only", "exempt")


def test_coverage_analyst_file_with_executable_code_is_missed() -> None:
    has_all("coverage-analyst", "executable code", "missed")


def test_coverage_analyst_is_strict_about_exempt() -> None:
    has_all("coverage-analyst", "strict about exempt")


def test_coverage_analyst_prefers_missed_when_a_fake_or_mock_would_reach_it() -> None:
    has_all("coverage-analyst", "fake", "mock", "dependency injection")


def test_coverage_analyst_report_has_blocks_lines() -> None:
    block = _report_block("coverage-analyst")
    assert "BLOCKS:" in block
    for cls in ("missed", "exempt", "not-in-spec"):
        assert cls in block


def test_coverage_analyst_report_has_exempt_file_line() -> None:
    assert "exempt-file" in _report_block("coverage-analyst")


# --- journey-test-writer -----------------------------------------------------------------


def test_journey_test_writer_one_test_per_journey_named_after_it() -> None:
    has_all("journey-test-writer", "one", "per journey", "named after")


def test_journey_test_writer_places_tests_where_the_stack_rules_say() -> None:
    has_all("journey-test-writer", "where the stack rules say")


def test_journey_test_writer_follows_steps_literally() -> None:
    has_all("journey-test-writer", "literally")


def test_journey_test_writer_steps_cover_screens_tools_and_services() -> None:
    has_all("journey-test-writer", "screens", "tool", "service")


def test_journey_test_writer_asserts_the_end_state() -> None:
    has_all("journey-test-writer", "end state")


def test_journey_test_writer_failure_paths_are_separate_tests() -> None:
    has_all("journey-test-writer", "failure path", "separate")


def test_journey_test_writer_finds_elements_by_test_identifiers() -> None:
    has_all("journey-test-writer", "identifier")


def test_journey_test_writer_missing_identifier_is_blocked_naming_the_screen() -> None:
    has_all("journey-test-writer", "missing", "blocked", "screen")


def test_journey_test_writer_starts_from_a_clean_state() -> None:
    has_all("journey-test-writer", "clean state")


def test_journey_test_writer_blocked_when_clean_state_is_impossible() -> None:
    after("journey-test-writer", "clean state", "blocked")


def test_journey_test_writer_cross_part_addresses_come_from_bull() -> None:
    has_all("journey-test-writer", "parts", "address", "bull")


def test_journey_test_writer_feature_mode() -> None:
    has_all("journey-test-writer", "MODE: feature <slug>")


def test_journey_test_writer_adopt_baseline_reports_app_misbehaviour_as_fail() -> None:
    has_all("journey-test-writer", "MODE: adopt-baseline", "fail")
    after("journey-test-writer", "mode: adopt-baseline", "fail")


def test_journey_test_writer_runs_the_journeys_gate() -> None:
    has_all("journey-test-writer", "bull gates --journeys")


def test_journey_test_writer_report_has_journeys_lines_pass_or_fail() -> None:
    block = _report_block("journey-test-writer")
    assert "JOURNEYS:" in block
    assert "pass" in block
    assert "fail" in block
    assert "blocked" in block
