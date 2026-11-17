"""Content of agents/surveyor.md and agents/legacy-test-scanner.md."""

from __future__ import annotations

import re

import pytest

from bull.Modules.plugin_text.plugin_files import LivePluginText

AGENTS = ("surveyor", "legacy-test-scanner")

DESCRIPTIONS = {
    "surveyor": (
        "Adoption stage 2. Read-only survey of an existing app's code, one bounded pass "
        "at a time (screens, data, services, a candidate module, or tests), so the "
        "orchestrator can write the memo."
    ),
    "legacy-test-scanner": (
        "Stage 5. Compares a module's old tests (an adoption's legacy tests, or a "
        "rewrite's reference tests) with its new spec-based tests and lists the cases "
        "the new ones miss."
    ),
}

TOOLS = {
    "surveyor": ("Read", "Grep", "Glob", "Bash"),
    "legacy-test-scanner": ("Read", "Grep", "Glob"),
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


# --- both agents -------------------------------------------------------------------------


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
def test_report_block_is_fenced_and_starts_with_status(name: str) -> None:
    assert "done" in _report_block(name)


@pytest.mark.parametrize("name", AGENTS)
def test_never_modifies_files(name: str) -> None:
    has_any(name, "never modify", "do not modify", "never modifies")


# --- surveyor ----------------------------------------------------------------------------


def test_surveyor_has_a_stack_rules_section_naming_command_and_part_flag() -> None:
    section = _norm(_section("surveyor", "Stack rules"))
    assert "bull stack rules surveyor" in section
    assert "--part" in section


def test_surveyor_describes_what_the_code_does_today() -> None:
    has_all("surveyor", "does today")


def test_surveyor_inputs_are_pass_file_list_and_inventory_lines() -> None:
    has_all("surveyor", "PASS", "inventory")
    has_any("surveyor", "files to read", "file list", "list of files")


def test_surveyor_inventory_lines_come_from_bull_adopt_legacy() -> None:
    has_all("surveyor", "bull adopt legacy")


def test_surveyor_never_names_bull_stack_inventory() -> None:
    assert "bull stack inventory" not in _norm(_raw("surveyor"))


def test_surveyor_lists_unread_files_under_not_read() -> None:
    has_all("surveyor", "NOT READ")


@pytest.mark.parametrize(
    "term", ["screens", "data", "services", "module <name>", "tests"]
)
def test_surveyor_has_each_of_the_five_passes(term: str) -> None:
    has_all("surveyor", term)


def test_surveyor_screens_pass_covers_flow_and_journeys() -> None:
    has_all("surveyor", "navigation", "journeys", "accessibility")


def test_surveyor_data_pass_covers_models_and_persistence() -> None:
    has_all("surveyor", "models", "persistence", "migrations")


def test_surveyor_services_pass_covers_networking_and_permissions() -> None:
    has_all("surveyor", "networking", "permissions", "retries")


def test_surveyor_module_pass_has_a_behavior_spec_and_how_files_split() -> None:
    has_all("surveyor", "behavior spec", "singletons")
    has_any("surveyor", "could split", "how its files")


def test_surveyor_tests_pass_names_the_candidate_module() -> None:
    has_all("surveyor", "candidate module")


def test_surveyor_rule_facts_carry_file_line_evidence() -> None:
    has_all("surveyor", "file:line")


def test_surveyor_rule_guesses_are_marked() -> None:
    has_all("surveyor", "guess")


def test_surveyor_rule_suspected_issues_are_listed_not_fixed() -> None:
    has_all("surveyor", "SUSPECTED ISSUES")
    has_any("surveyor", "without fixing", "not fix", "never fix")


def test_surveyor_proposes_no_redesign() -> None:
    has_all("surveyor", "redesign")


def test_surveyor_report_has_its_fields() -> None:
    block = _report_block("surveyor")
    for field in ("STATUS:", "PASS:", "FINDINGS:", "SUSPECTED ISSUES:", "NOT READ:"):
        assert field in block, field


def test_surveyor_report_status_is_done_or_partial() -> None:
    block = _report_block("surveyor")
    assert "done" in block
    assert "partial" in block


# --- legacy-test-scanner -----------------------------------------------------------------


def test_scanner_does_not_run_bull_stack_rules() -> None:
    assert "bull stack rules" not in _norm(_raw("legacy-test-scanner"))


def test_scanner_never_opens_implementation_files() -> None:
    has_all("legacy-test-scanner", "implementation")
    has_any("legacy-test-scanner", "never open", "do not open", "never read")


def test_scanner_has_adopt_mode_reading_the_legacy_tests_line() -> None:
    has_all("legacy-test-scanner", "MODE: adopt", "Legacy tests:")


def test_scanner_has_reference_mode_reading_the_reference_tests_line() -> None:
    has_all("legacy-test-scanner", "MODE: reference", "Reference tests:")


def test_scanner_reference_mode_reads_inside_the_reference_folder() -> None:
    after("legacy-test-scanner", "mode: reference", "reference folder")


def test_scanner_is_the_only_agent_that_reads_the_reference_folder() -> None:
    has_all("legacy-test-scanner", "only agent")


def test_scanner_compares_behavior_not_names() -> None:
    has_all("legacy-test-scanner", "behavior")
    has_any("legacy-test-scanner", "not names", "not by name", "not the name")


def test_scanner_checks_each_case_not_each_test_function() -> None:
    has_any("legacy-test-scanner", "each assertion", "each case")


@pytest.mark.parametrize(
    "cls", ["covered", "missed", "contradicts", "not-in-spec", "obsolete"]
)
def test_scanner_names_each_of_the_five_classes(cls: str) -> None:
    has_all("legacy-test-scanner", cls)


def test_scanner_missed_is_named_in_the_specs_terms() -> None:
    has_all("legacy-test-scanner", "in the spec's terms")


def test_scanner_missed_is_never_copied_from_the_old_test() -> None:
    has_any("legacy-test-scanner", "never by copying", "never copy", "not copy")


def test_scanner_covered_says_which_new_test_checks_it() -> None:
    has_all("legacy-test-scanner", "covered")
    has_any("legacy-test-scanner", "say which", "name which", "which new test")


def test_scanner_contradicts_quotes_both_sides() -> None:
    has_all("legacy-test-scanner", "contradicts", "quote")


def test_scanner_obsolete_is_an_implementation_detail_the_redesign_removes() -> None:
    has_all("legacy-test-scanner", "obsolete", "redesign")


def test_scanner_report_has_cases_lines() -> None:
    block = _report_block("legacy-test-scanner")
    assert "STATUS:" in block
    assert "CASES:" in block


def test_scanner_report_ends_with_the_counts_line() -> None:
    lines = [ln.strip() for ln in _report_block("legacy-test-scanner").split("\n")]
    lines = [ln for ln in lines if ln]
    assert lines[-1].startswith("COUNTS:")


def test_scanner_counts_line_has_the_four_refscan_counts() -> None:
    counts = next(
        ln
        for ln in _report_block("legacy-test-scanner").split("\n")
        if ln.strip().startswith("COUNTS:")
    )
    for word in ("covered", "missed", "contradicts", "not-in-spec"):
        assert word in counts, word


def test_scanner_counts_line_is_recorded_with_bull_status_refscan() -> None:
    has_all("legacy-test-scanner", "bull status refscan")
