"""Content of agents/skeleton-builder.md, screen-builder.md, test-writer.md and code-writer.md."""

from __future__ import annotations

import re

import pytest

from bull.Modules.plugin_text.plugin_files import LivePluginText

AGENTS = ("skeleton-builder", "screen-builder", "test-writer", "code-writer")

DESCRIPTIONS = {
    "skeleton-builder": (
        "Stage 3. Builds the compiling skeleton from the memo — module folders, contracts, "
        "stubs, mocks. Also a feature's skeleton (MODE: feature) and an adoption's scaffold "
        "(MODE: adopt)."
    ),
    "screen-builder": (
        "Stage 4. Builds or revises one screen and its view model against protocol mocks. "
        "Use for prototype screens and UI feedback."
    ),
    "test-writer": (
        "Stage 5. Writes unit tests for the files of one work unit from the memo's spec, "
        "before or without seeing the implementation."
    ),
    "code-writer": (
        "Stage 5. Implements the source files of one work unit so their existing tests pass. "
        "Cannot edit tests."
    ),
}

TOOLS = ("Read", "Write", "Edit", "Grep", "Glob", "Bash")


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
    assert doc.tools == TOOLS


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
    assert "more specific" in section


@pytest.mark.parametrize("name", AGENTS)
def test_report_block_is_fenced_and_starts_with_status(name: str) -> None:
    block = _report_block(name)
    assert "done" in block
    assert "blocked" in block


@pytest.mark.parametrize("name", AGENTS)
def test_report_block_lists_files(name: str) -> None:
    assert "FILES" in _report_block(name)


@pytest.mark.parametrize("name", AGENTS)
def test_question_block_has_its_four_lines(name: str) -> None:
    norm = _body(name)
    for field in ("ASK:", "WHY:", "OPTIONS:", "RECOMMEND:"):
        assert field in norm, f"{name}: no {field}"
    assert "QUESTION" in norm


@pytest.mark.parametrize("name", AGENTS)
def test_question_says_the_human_sees_none_of_your_files(name: str) -> None:
    has_all(name, "the human sees none of your files")


# --- skeleton-builder --------------------------------------------------------------------


def test_skeleton_builder_layout_names_source_dir_modules_and_contracts() -> None:
    has_all("skeleton-builder", "<source_dir>/Modules/<Module>/", "Contracts/")


def test_skeleton_builder_layout_names_test_dir_per_module() -> None:
    has_all("skeleton-builder", "<test_dir>/<Module>/")


def test_skeleton_builder_reads_layout_from_the_config() -> None:
    has_all("skeleton-builder", ".bull/config.toml")


def test_skeleton_builder_stubs_fail_loudly_with_not_implemented() -> None:
    has_all("skeleton-builder", "Not implemented")


def test_skeleton_builder_writes_mocks_with_realistic_data_recording_calls() -> None:
    has_all("skeleton-builder", "mock", "realistic", "record")


def test_skeleton_builder_writes_one_placeholder_test_per_implementation_file() -> None:
    has_all(
        "skeleton-builder", "placeholder test", "one test file per implementation file"
    )


def test_skeleton_builder_puts_project_settings_in_manual_steps_for_human() -> None:
    has_all("skeleton-builder", "MANUAL STEPS FOR HUMAN")


def test_skeleton_builder_checks_with_gates_all_skip_coverage() -> None:
    has_all("skeleton-builder", "bull gates --all --skip-coverage")


def test_skeleton_builder_puts_data_models_in_the_foundational_modules_contracts() -> (
    None
):
    has_all("skeleton-builder", "foundational")


def test_skeleton_builder_writes_protocols_exactly_as_drafted() -> None:
    has_all("skeleton-builder", "exactly as drafted")


def test_skeleton_builder_creates_interface_files_only_if_the_memo_says_so() -> None:
    has_all("skeleton-builder", "## Interfaces")


def test_skeleton_builder_report_lists_manual_steps_question_and_notes() -> None:
    block = _report_block("skeleton-builder")
    for field in ("MANUAL STEPS FOR HUMAN", "QUESTION", "NOTES"):
        assert field in block


def test_skeleton_builder_feature_mode_uses_mode_line_and_feature_stubs() -> None:
    has_all("skeleton-builder", "MODE: feature <slug>", "(feature <slug>)")


def test_skeleton_builder_feature_mode_marks_changed_signatures_in_tests() -> None:
    has_all("skeleton-builder", "signature updated")


def test_skeleton_builder_adopt_mode_has_rename_and_scaffold_steps() -> None:
    has_all("skeleton-builder", "MODE: adopt", "STEP: rename", "STEP: scaffold")


def test_skeleton_builder_adopt_mode_writes_no_stubs() -> None:
    has_any(
        "skeleton-builder", "no stubs", "not write stubs", "without stubs", "no stub"
    )


def test_skeleton_builder_adopt_mode_names_the_composition_root_from_legacy_code() -> (
    None
):
    has_all("skeleton-builder", "composition root", "## Legacy code")


def test_skeleton_builder_never_changes_legacy_code_beyond_renames() -> None:
    has_all("skeleton-builder", "legacy code", "renames")


def test_skeleton_builder_rules_forbid_inventing_modules() -> None:
    has_any("skeleton-builder", "do not invent", "never invent", "don't invent")


def test_skeleton_builder_blocked_when_the_memo_is_missing_something() -> None:
    has_all("skeleton-builder", "blocked", "memo")


# --- screen-builder ----------------------------------------------------------------------


def test_screen_builder_puts_view_files_where_the_stack_rules_say() -> None:
    has_all("screen-builder", "view file", "stack rules")


def test_screen_builder_view_model_sits_with_the_modules_other_files() -> None:
    has_all("screen-builder", "view model")


def test_screen_builder_depends_on_protocols_only() -> None:
    has_all("screen-builder", "protocol")


def test_screen_builder_previews_use_the_mocks() -> None:
    has_all("screen-builder", "preview", "mock")


def test_screen_builder_navigation_follows_the_memo() -> None:
    has_all("screen-builder", "navigation", "memo")


def test_screen_builder_sets_accessibility_and_test_identifiers() -> None:
    has_all("screen-builder", "accessibility", "identifier")


def test_screen_builder_adopt_identifiers_mode_adds_identifiers_only() -> None:
    has_all("screen-builder", "MODE: adopt-identifiers", "identifiers only")


def test_screen_builder_adopt_identifiers_checks_with_gates_skip_coverage() -> None:
    has_all("screen-builder", "bull gates --all --skip-coverage")


def test_screen_builder_protocol_change_means_blocked() -> None:
    has_all("screen-builder", "protocol", "blocked")
    has_any(
        "screen-builder", "change a protocol", "protocol change", "changing a protocol"
    )


def test_screen_builder_keeps_business_logic_out_of_views() -> None:
    has_all("screen-builder", "business logic")


# --- test-writer -------------------------------------------------------------------------


def test_test_writer_reads_only_the_briefs_files() -> None:
    has_all("test-writer", "your brief")
    has_any("test-writer", "read only", "only the brief", "only what the brief")


def test_test_writer_never_opens_the_implementation() -> None:
    has_all("test-writer", "do not open the implementation")


def test_test_writer_writes_one_test_file_per_source_file_in_the_test_dir() -> None:
    has_all("test-writer", "one test file per source file", "<test_dir>/<Module>/")


def test_test_writer_writes_a_test_for_every_spec_behavior() -> None:
    has_all("test-writer", "every behavior", "behavior spec")


def test_test_writer_covers_error_cases_and_boundaries() -> None:
    has_all("test-writer", "error case", "boundar")


def test_test_writer_uses_mocks_or_in_memory_fakes() -> None:
    has_all("test-writer", "mock", "fake")


def test_test_writer_uses_a_unique_temporary_folder_per_test() -> None:
    has_all("test-writer", "unique temporary")


def test_test_writer_names_tests_by_behavior() -> None:
    has_all("test-writer", "name tests by the behavior")


def test_test_writer_replaces_the_placeholder_test() -> None:
    has_all("test-writer", "replace the placeholder")


def test_test_writer_tests_compile_against_the_contract() -> None:
    has_all("test-writer", "contract")


def test_test_writer_ambiguous_spec_returns_blocked_with_the_question() -> None:
    has_all("test-writer", "ambiguous", "blocked")


def test_test_writer_coverage_triage_briefs_name_the_behaviors_to_test() -> None:
    has_all("test-writer", "coverage-triage", "exactly those")


def test_test_writer_never_opens_the_reference_folder() -> None:
    has_all("test-writer", "reference")
    has_any("test-writer", "never open the reference", "do not open the reference")


def test_test_writer_runs_formatter_and_lint_on_its_test_files_before_reporting() -> (
    None
):
    has_all("test-writer", "before you report", "formatter", "lint")
    has_any("test-writer", "wrote or changed", "written or changed")


def test_test_writer_fixes_what_formatter_and_lint_find() -> None:
    has_all("test-writer", "fix")
    in_order("test-writer", "formatter", "lint", "fix")


def test_test_writer_formatter_rule_names_no_specific_tool() -> None:
    section = _norm(_body("test-writer"))
    assert "ruff" not in section
    assert "stack rules name" in section or "stack's rules name" in section


def test_test_writer_change_mode_updates_changed_tests_and_leaves_the_rest() -> None:
    has_all("test-writer", "CHANGE: <slug>", "leave every other test")


def test_test_writer_change_mode_may_read_the_existing_tests() -> None:
    has_all("test-writer", "existing test")


def test_test_writer_change_mode_replaces_signature_updated_calls() -> None:
    has_all("test-writer", "signature updated")


def test_test_writer_adopt_legacy_cases_writes_the_listed_behaviors() -> None:
    has_all("test-writer", "ADOPT: legacy cases")


def test_test_writer_adopt_switch_over_deletes_and_repoints_then_runs_fast_gates() -> (
    None
):
    has_all("test-writer", "ADOPT: switch-over", "delete", "repoint")
    in_order("test-writer", "ADOPT: switch-over", "bull gates <Module> --fast")


def test_test_writer_adopt_baseline_fixes_or_disables_named_tests_only() -> None:
    has_all("test-writer", "ADOPT: baseline", "disable")


def test_test_writer_partial_report_has_done_and_remaining() -> None:
    block = _report_block("test-writer")
    assert "partial" in block
    assert "DONE" in block
    assert "REMAINING" in block


def test_test_writer_partial_stops_after_a_whole_file() -> None:
    has_all("test-writer", "partial", "whole file")


def test_test_writer_report_lists_behaviors_covered() -> None:
    assert "BEHAVIORS COVERED" in _report_block("test-writer")


def test_test_writer_stack_mode_writes_fixture_and_cases_json() -> None:
    has_all("test-writer", "MODE: stack", "fixture/", "cases.json", "DESIGN.md")


def test_test_writer_stack_mode_checks_with_stack_test_static() -> None:
    has_all("test-writer", "bull stack test . --static")


def test_test_writer_stack_mode_has_no_stack_rules_yet() -> None:
    has_all("test-writer", "Stack files")


# --- code-writer -------------------------------------------------------------------------


def test_code_writer_write_rules_say_reference_cycles() -> None:
    has_all("code-writer", "reference cycles")


def test_code_writer_write_rules_say_crashing_shortcuts() -> None:
    has_all("code-writer", "crashing shortcuts")


def test_code_writer_uses_no_platform_flavoured_phrases() -> None:
    norm = _norm(_body("code-writer"))
    assert "retain cycle" not in norm
    assert "force unwrap" not in norm


def test_code_writer_contracts_are_off_limits() -> None:
    has_all("code-writer", "Contracts/")
    has_any("code-writer", "off limits", "never edit", "do not edit", "do not change")


def test_code_writer_reaches_other_modules_only_through_their_contracts() -> None:
    has_all("code-writer", "other modules", "only through")


def test_code_writer_uses_only_the_dependencies_the_brief_lists() -> None:
    has_all("code-writer", "listed")


def test_code_writer_documents_contract_declarations_and_tricky_logic() -> None:
    has_all("code-writer", "document", "tricky")


def test_code_writer_change_mode_changes_the_existing_implementation() -> None:
    has_all("code-writer", "CHANGE: <slug>")


def test_code_writer_has_the_three_adopt_modes() -> None:
    has_all("code-writer", "ADOPT: unit", "ADOPT: switch-over", "ADOPT: baseline")


def test_code_writer_adopt_unit_may_read_the_legacy_files_listed() -> None:
    has_all("code-writer", "LEGACY FILES")


def test_code_writer_adopt_switch_over_repoints_callers_and_deletes_replaced_code() -> (
    None
):
    has_all("code-writer", "CALLERS", "repoint", "delete")


def test_code_writer_checks_with_fast_gates() -> None:
    has_all("code-writer", "bull gates <Module> --fast")


def test_code_writer_iterates_with_failed_then_finishes_with_fast() -> None:
    in_order("code-writer", "bull gates --failed", "--fast")


def test_code_writer_partial_report_has_done_and_remaining() -> None:
    block = _report_block("code-writer")
    assert "partial" in block
    assert "DONE" in block
    assert "REMAINING" in block


def test_code_writer_cannot_edit_test_files_because_bull_blocks_it() -> None:
    has_all("code-writer", "cannot edit", "bull blocks")


def test_code_writer_a_wrong_test_means_blocked() -> None:
    has_all("code-writer", "wrong", "blocked")


def test_code_writer_a_needed_contract_change_means_blocked() -> None:
    has_all("code-writer", "contract change", "blocked")


def test_code_writer_never_opens_the_reference_folder() -> None:
    has_all("code-writer", "reference")
    has_any("code-writer", "never open the reference", "do not open the reference")


def test_code_writer_stack_mode_writes_gate_program_readers_and_docs() -> None:
    has_all(
        "code-writer", "MODE: stack", "readers.py", "setup.md", "rules.md", "DESIGN.md"
    )


def test_code_writer_stack_mode_names_the_gate_program() -> None:
    has_all("code-writer", "gate program")


def test_code_writer_stack_mode_checks_with_stack_test() -> None:
    has_all("code-writer", "bull stack test .")


def test_code_writer_stack_mode_uses_the_stack_files_section() -> None:
    has_all("code-writer", "Stack files")
