"""Content of orchestrator.md: every section the source note lists, and what it must say."""

from __future__ import annotations

import re

import pytest

from bull.Modules.plugin_text.plugin_files import LivePluginText

_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")


def _norm(text: str) -> str:
    """Lower-case, backticks dropped, whitespace collapsed."""
    return re.sub(r"\s+", " ", text.replace("`", "")).strip().lower()


def _raw() -> str:
    return LivePluginText().orchestrator()


def _headings(text: str) -> list[tuple[int, int, str]]:
    """(line index, level, heading text), skipping lines inside fenced blocks."""
    out: list[tuple[int, int, str]] = []
    fenced = False
    for i, line in enumerate(text.split("\n")):
        if re.match(r"^[ \t]*(```|~~~)", line):
            fenced = not fenced
            continue
        m = None if fenced else _HEADING.match(line)
        if m:
            out.append((i, len(m.group(1)), m.group(2)))
    return out


def section(key: str) -> str:
    """Raw text of the first heading matching `key` (regex, case-insensitive), up to the
    next heading of the same or a higher level."""
    text = _raw()
    lines = text.split("\n")
    heads = _headings(text)
    for n, (idx, level, title) in enumerate(heads):
        if re.search(key, title, re.IGNORECASE):
            end = len(lines)
            for idx2, level2, _ in heads[n + 1 :]:
                if level2 <= level:
                    end = idx2
                    break
            return "\n".join(lines[idx:end])
    raise AssertionError(f"no heading matching {key!r}")


def has_all(text: str, *terms: str) -> None:
    norm = _norm(text)
    missing = [t for t in terms if t.lower() not in norm]
    assert not missing, f"missing: {missing}"


def in_order(text: str, *terms: str) -> None:
    norm = _norm(text)
    pos = 0
    for t in terms:
        found = norm.find(t.lower(), pos)
        assert found >= 0, f"{t!r} missing or out of order (after position {pos})"
        pos = found + len(t)


def numbered_items(text: str) -> dict[int, str]:
    """Top-level `N.` items of a list, keyed by number (text up to the next item)."""
    lines = text.split("\n")
    items: dict[int, list[str]] = {}
    current: int | None = None
    for line in lines:
        m = re.match(r"^(\d+)[.)][ \t]+(.*)$", line)
        if m:
            current = int(m.group(1))
            items[current] = [m.group(2)]
        elif current is not None:
            items[current].append(line)
    return {k: "\n".join(v) for k, v in items.items()}


# --- structure ---------------------------------------------------------------------------


def test_title_is_bull_orchestrator_instructions() -> None:
    first = next(line for line in _raw().split("\n") if line.strip())
    assert re.match(r"^#\s+bull\W+orchestrator instructions\s*$", first, re.IGNORECASE)


@pytest.mark.parametrize(
    "key",
    [
        r"golden rules",
        r"^files",
        r"safeguards",
        r"stages",
        r"delegating",
        r"asking the human",
        r"stage 5 loop",
        r"interfaces",
        r"feature cycle",
        r"adopting",
        r"handing off",
        r"^never",
    ],
)
def test_section_heading_is_present(key: str) -> None:
    assert section(key).strip()


def test_sections_come_in_the_order_the_note_gives() -> None:
    keys = [
        r"golden rules",
        r"^files",
        r"safeguards",
        r"stages",
        r"delegating",
        r"asking the human",
        r"stage 5 loop",
        r"interfaces",
        r"feature cycle",
        r"adopting",
        r"handing off",
        r"^never",
    ]
    heads = _headings(_raw())
    positions = []
    for key in keys:
        positions.append(
            next(i for i, _, t in heads if re.search(key, t, re.IGNORECASE))
        )
    assert positions == sorted(positions)


# --- intro -------------------------------------------------------------------------------


def test_intro_says_the_orchestrator_role_and_the_stages() -> None:
    has_all(
        _raw(),
        "orchestrator",
        "stages",
        "bull stacks",
        "never write app code",
    )
    has_all(_raw(), "discuss", "outline", "setup", "skeleton", "prototype", "verify")


def test_intro_says_where_things_live() -> None:
    has_all(_raw(), "where things live", "bull <command>", ".bull/plugin/", "bull open")


def test_intro_says_stack_specific_things_come_from_the_stack() -> None:
    has_all(_raw(), "bull stack rules outline", "bull stack rules <agent>")


def test_intro_explains_parts() -> None:
    has_all(
        _raw(),
        "bull part list",
        "- part:",
        "part: <name> (<stack>)",
        "bull stack rules <agent> --part <name>",
        "another part",
        "interfaces",
    )


# --- golden rules ------------------------------------------------------------------------


def test_golden_rules_are_numbered_one_to_eight() -> None:
    items = numbered_items(section(r"golden rules"))
    assert sorted(items) == list(range(1, 9))


def test_rule_1_one_subagent_at_a_time() -> None:
    has_all(numbered_items(section(r"golden rules"))[1], "one subagent", "parallel")


def test_rule_2_files_are_the_memory() -> None:
    has_all(
        numbered_items(section(r"golden rules"))[2],
        "docs/outline.md",
        ".bull/status.json",
        ".bull/backlog.json",
        "git",
    )


def test_rule_3_only_the_orchestrator_talks_to_the_human() -> None:
    has_all(
        numbered_items(section(r"golden rules"))[3],
        "only you talk to the human",
        "asking the human",
    )


def test_rule_4_only_the_orchestrator_edits_memo_merges_and_status() -> None:
    has_all(numbered_items(section(r"golden rules"))[4], "memo", "merge", "bull status")


def test_rule_5_contract_changes_need_approval() -> None:
    has_all(
        numbered_items(section(r"golden rules"))[5],
        "approval",
        "bull status wait",
        "bull status approve",
        "bull api",
        "--write",
        "--interface",
        "contracts/",
        "contract changes (<slug>)",
    )


def test_rule_6_attempts_cap_at_max_attempts() -> None:
    has_all(
        numbered_items(section(r"golden rules"))[6],
        "max_attempts",
        "3",
        "bull status attempt",
        "bull status unblock",
    )


def test_rule_7_commit_after_every_completed_step() -> None:
    has_all(numbered_items(section(r"golden rules"))[7], "commit", "step")


def test_rule_8_stop_at_step_boundaries_on_pause() -> None:
    has_all(
        numbered_items(section(r"golden rules"))[8],
        "bull status usage-check",
        "pause",
        'bull status pause "<reason>"',
        "usage resets",
        "unknown",
    )


# --- files -------------------------------------------------------------------------------


def test_files_table_names_every_file_and_who_edits_it() -> None:
    has_all(
        section(r"^files"),
        "docs/outline.md",
        "docs/api/<module>.md",
        "docs/api/interfaces/<name>.md",
        ".bull/status.json",
        ".bull/backlog.json",
        ".bull/config.toml",
        ".bull/parts/<part>.toml",
        "bull config set",
        ".bull/usage.json",
        "docs/features/<slug>.md",
        "bull feature add",
        "<source_dir>/modules/<module>/",
        "<test_dir>/<module>/",
        "interfaces/",
        "reference_dir",
        "reference/",
        "legacy-test-scanner",
    )


def test_progress_gauge_uses_status_plan_and_tick() -> None:
    has_all(
        _raw(),
        "progress gauge",
        "bull status plan <label>",
        "bull status tick",
        "bull status plan <label> --clear",
    )


# --- safeguards --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "terms",
    [
        ("usage guard", "pause"),
        ("approval wait", "waiting"),
        ("merge guard", "full gate pass", "reference tests", "scan"),
        ("test protection", "code-writer", "test files"),
        ("reference protection", "test-writer", "reference"),
    ],
)
def test_safeguard_is_described(terms: tuple[str, ...]) -> None:
    has_all(section(r"safeguards"), *terms)


def test_safeguards_that_cannot_run_fail_closed() -> None:
    has_all(section(r"safeguards"), "fails closed", "never work around")


# --- stages and commands -----------------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        "/bull:discuss",
        "/bull:outline",
        "/bull:setup",
        "/bull:skeleton",
        "/bull:prototype",
        "/bull:build",
        "/bull:verify",
    ],
)
def test_stages_table_names_each_stage_command(command: str) -> None:
    table = [ln for ln in section(r"stages").split("\n") if ln.lstrip().startswith("|")]
    assert any(command in ln for ln in table)


@pytest.mark.parametrize(
    "command", ["/bull:resume", "/bull:status", "/bull:adopt", "/bull:feature"]
)
def test_stages_section_names_the_other_commands(command: str) -> None:
    has_all(section(r"stages"), command)


def test_stages_section_names_the_checkpoint_tags() -> None:
    has_all(
        section(r"stages"),
        "outline-approved",
        "setup",
        "skeleton",
        "ui-approved",
        "module/<m>",
        "app-accepted",
        "bull stack check",
    )


def test_stages_section_says_the_human_starts_each_stage() -> None:
    has_all(
        section(r"stages"),
        "human starts each stage",
        "bull status next",
        "checkpoint 3",
    )


# --- delegating --------------------------------------------------------------------------


def _brief_block() -> str:
    blocks = re.findall(
        r"^[ \t]*```[^\n]*\n(.*?)^[ \t]*```",
        section(r"delegating"),
        re.DOTALL | re.MULTILINE,
    )
    for b in blocks:
        if "TASK:" in b:
            return str(b)
    raise AssertionError("no fenced brief template with a TASK: line")


def test_brief_template_is_a_fenced_block_with_every_field_in_order() -> None:
    block = _brief_block()
    pos = 0
    for field in [
        "TASK:",
        "MODULE:",
        "UNIT:",
        "ATTEMPT:",
        "PART:",
        "READ ONLY THESE:",
        "ACCEPTANCE:",
        "PREVIOUS FAILURE",
        "RETURN:",
    ]:
        found = block.find(field, pos)
        assert found >= 0, f"{field} missing or out of order"
        pos = found + len(field)


def test_brief_template_reads_only_memo_sections_and_dependency_contracts() -> None:
    block = _brief_block()
    assert "docs/outline.md" in block
    assert "docs/api/" in block
    assert "max_attempts" in block


def test_optional_brief_lines_are_listed() -> None:
    delegating = section(r"delegating")
    for term in [
        "CHANGE: <slug>",
        "ADOPT:",
        "LEGACY FILES",
        "CALLERS",
        "MODE:",
        "SCOPE:",
        "CATEGORIES:",
    ]:
        assert term in delegating, term


def test_brief_is_the_boundary_and_reference_folder_is_never_listed() -> None:
    has_all(
        section(r"delegating"),
        "the brief is the boundary",
        "reviewer checks for leaks",
        "reference",
        "test-writer",
        "code-writer",
        "bull blocks",
    )


def test_units_and_context_partial_reports() -> None:
    has_all(
        section(r"delegating"),
        "max_files_per_unit",
        "status: partial",
        "done",
        "remaining",
        "no attempt used",
        "blocked",
        "question:",
        "ask",
        "why",
        "options",
        "recommend",
    )


# --- asking the human --------------------------------------------------------------------


def test_asking_the_human_lists_the_six_parts_in_order() -> None:
    in_order(
        section(r"asking the human"),
        "where we are",
        "what happened",
        "why it needs you",
        "options",
        "recommendation",
        "what happens next",
    )


def test_asking_the_human_says_what_to_quote_and_which_rule() -> None:
    has_all(
        section(r"asking the human"),
        "file:line",
        "one line per attempt",
        "rule",
        "two to four",
        "cost",
    )


def test_asking_the_human_rules_on_wording_and_approvals() -> None:
    has_all(
        section(r"asking the human"),
        "plain words",
        "first time",
        "one decision per question",
        "number",
        "multiple-choice",
        "approvals",
        "what changed",
        "decisions log",
    )


# --- stage 5 loop ------------------------------------------------------------------------


def test_stage_5_loop_runs_its_steps_in_the_documented_order() -> None:
    in_order(
        section(r"stage 5 loop"),
        "git switch -c",
        "bull status module",
        "in_progress",
        "test-writer",
        "bull status unit <m> <n> tests",
        "code-writer",
        "bull gates <m> --fast",
        "bull status attempt",
        "bull status unit <m> <n> code",
        "reviewer",
        "bull status unit <m> <n> done",
        "bull status refscan",
        "--coverage-report",
        "git merge --no-ff",
        "--after-merge",
        "bull api",
        "--write",
        "git tag",
        "bull status module <m> done",
        "bull gates --all",
    )


def test_stage_5_loop_names_branches_and_tags_from_status_ref() -> None:
    has_all(
        section(r"stage 5 loop"),
        "bull status ref",
        "base_branch",
        "feature/<slug>/main",
        "adopt/main",
        "bull status ref tag module/<m>",
    )


def test_stage_5_loop_commit_messages_for_tests_and_unit() -> None:
    has_all(
        section(r"stage 5 loop"),
        "test(<m>): unit <n> tests",
        "feat(<m>): unit <n>",
    )


def test_stage_5_loop_handles_partial_failed_gates_and_review_modes() -> None:
    has_all(
        section(r"stage 5 loop"),
        "partial",
        "remaining",
        "cannot edit tests",
        "bull gates --failed",
        "golden rule 5",
        "review_mode",
        "combined",
        "split",
        "scope:",
        "blocker",
    )


def test_reference_test_scan_follows_the_reviewed_units() -> None:
    text = section(r"stage 5 loop")
    has_all(
        text,
        "reference tests:",
        "bull status next",
        "legacy-test-scanner",
        "mode: reference",
        "covered",
        "missed",
        "contradicts",
        "not-in-spec",
        "from the spec",
        "never the old test",
        "decisions log",
        "--covered",
        "--missed",
        "--contradicts",
        "--not-in-spec",
        "merge guard",
    )


def test_coverage_triage_classifications() -> None:
    has_all(
        section(r"stage 5 loop"),
        "coverage triage",
        "coverage-analyst",
        "missed",
        "exempt",
        "coverage-exempt",
        "coverage-exempt-file",
        "reviewer",
        "not-in-spec",
        "repeat until clean",
    )


def _triage_step() -> str:
    """Normalized text of the loop's coverage-triage step (up to the full-gates step)."""
    norm = _norm(section(r"stage 5 loop"))
    start = norm.index("coverage triage.")
    end = norm.index("bull gates <m>` without".replace("`", ""), start)
    return norm[start:end]


def _refscan_step() -> str:
    norm = _norm(section(r"stage 5 loop"))
    start = norm.index("reference-test scan.")
    return norm[start : norm.index("coverage triage.", start)]


def test_triage_names_defensive_as_a_coverage_analyst_class() -> None:
    step = _triage_step()
    has_all(step, "coverage-analyst", "missed", "exempt", "defensive", "not-in-spec")


def test_triage_reads_the_auto_approve_setting_with_config_show() -> None:
    has_all(
        _triage_step(),
        "coverage.auto_approve_defensive",
        "bull config show",
        "true",
    )


def test_triage_adds_defensive_case_to_spec_tests_it_and_logs_it() -> None:
    step = _triage_step()
    has_all(
        step,
        "behavior spec",
        "test-writer",
        "from the spec",
        "decisions log",
        "auto-approved (defensive)",
    )
    in_order(step, "defensive", "behavior spec", "test-writer", "decisions log")


def test_triage_does_not_ask_the_human_for_an_approved_defensive_case() -> None:
    assert re.search(
        r"(without asking|no question|not ask|without a question)", _triage_step()
    )


def _defensive_bullet() -> str:
    """Normalized text of the `defensive` bullet alone (up to the `not-in-spec` bullet)."""
    lines = section(r"stage 5 loop").split("\n")
    bullet = re.compile(r"^\s*[-*]\s+[*_]*`?{}`?")
    start = next(
        i
        for i, ln in enumerate(lines)
        if re.match(bullet.pattern.format("defensive"), ln)
    )
    end = next(
        i
        for i in range(start + 1, len(lines))
        if re.match(bullet.pattern.format("not-in-spec"), lines[i])
    )
    return _norm("\n".join(lines[start:end]))


def test_triage_reviewer_confirms_the_five_rules_for_defensive_cases() -> None:
    has_all(_defensive_bullet(), "reviewer", "five", "rules")


def test_triage_reviewer_confirms_before_spec_test_and_log() -> None:
    bullet = _defensive_bullet()
    in_order(
        bullet, "reviewer", "behavior spec", "test-writer", "auto-approved (defensive)"
    )


def test_triage_sends_rejected_or_setting_off_defensive_cases_to_the_human() -> None:
    bullet = _defensive_bullet()
    has_all(bullet, "false", "goes to the human", "not-in-spec")
    assert re.search(r"(fails|rejects|rejected|does not meet)", bullet)


def test_triage_not_in_spec_still_asks_the_human() -> None:
    has_all(_triage_step(), "not-in-spec", "ask the human", "remove the code")


def test_defensive_rule_lives_in_triage_not_in_the_reference_scan() -> None:
    scan = _refscan_step()
    assert "defensive" not in scan
    assert "auto_approve_defensive" not in scan
    assert "auto-approved" not in scan


def test_reference_scan_not_in_spec_still_goes_to_the_human() -> None:
    has_all(_refscan_step(), "contradicts", "not-in-spec", "ask the human")


def test_full_gates_run_sits_between_coverage_triage_and_the_merge() -> None:
    norm = _norm(section(r"stage 5 loop"))
    start = norm.index("--coverage-report") + len("--coverage-report")
    end = norm.index("git merge --no-ff")
    assert re.search(r"bull gates <[^>]+>(?!\s*--)", norm[start:end])
    has_all(section(r"stage 5 loop"), "records the pass", "clean tree")


def test_merge_is_a_no_ff_merge_of_the_module_branch_into_the_base() -> None:
    has_all(
        section(r"stage 5 loop"),
        "git switch <base> && git merge --no-ff <branch>",
        "bull gates --after-merge <branch>",
    )


def test_snapshot_step_updates_the_memo_contract_line() -> None:
    has_all(
        section(r"stage 5 loop"),
        "bull api <m> --write",
        "contract:",
        "docs/api/<m>.md",
        "commit",
    )


def test_after_the_last_module_the_whole_suite_runs_on_the_base() -> None:
    has_all(
        section(r"stage 5 loop"),
        "after the stage's last module",
        "bull gates --all",
        "owning module",
    )


# --- interfaces --------------------------------------------------------------------------


def test_interfaces_section_explains_interface_files_as_contracts() -> None:
    has_all(
        section(r"interfaces"),
        "## interfaces",
        "interfaces/<file>",
        "provider",
        "consumer",
        "bull api --interface <name> --write",
        "golden rule 5",
    )


def test_interfaces_are_gated_per_side_and_journeys_start_providers() -> None:
    has_all(
        section(r"interfaces"),
        "interface",
        "gate",
        "own stack",
        "before its provider exists",
        "journeys",
        "provider parts",
    )


def test_modules_never_import_another_parts_code() -> None:
    has_all(section(r"interfaces"), "never let a module import", "propose an interface")


# --- feature cycle -----------------------------------------------------------------------


def test_feature_cycle_queues_ideas_in_the_backlog() -> None:
    has_all(
        section(r"feature cycle"),
        "app-accepted",
        "/bull:feature",
        ".bull/backlog.json",
        "docs/features/",
        "one active at a time",
        "feature/<slug>/main",
        "human accepts",
    )


def test_feature_cycle_stage_and_checkpoints_belong_to_the_feature() -> None:
    has_all(
        section(r"feature cycle"),
        "bull status stage",
        "checkpoint",
        "feature/<slug>/",
    )


def test_feature_cycle_memo_marks_the_change() -> None:
    has_all(
        section(r"feature cycle"),
        "changes (<slug>): <files>",
        "contract changes (<slug>)",
        "bull feature plan",
        "new modules",
        "reopens",
    )


def test_feature_cycle_reopened_units_run_the_loop_with_change_brief() -> None:
    has_all(
        section(r"feature cycle"),
        "stage 5 loop",
        "change: <slug>",
        "agreed scope",
        "test-writer",
        "code-writer",
        "reviewer",
        "unchanged behavior still holds",
    )


def test_feature_cycle_verify_and_abandon() -> None:
    has_all(
        section(r"feature cycle"),
        "verify",
        "journey tests",
        "new and changed journeys",
        "runs all",
        "diff",
        "abandon",
        "untouched",
    )


# --- adopting ----------------------------------------------------------------------------


def test_adoption_branch_prefix_and_finish() -> None:
    has_all(
        section(r"adopting"),
        "adopt/main",
        "adopt/",
        "adopted",
        "bull adopt finish",
    )


def test_adoption_stages_and_checkpoints() -> None:
    has_all(
        section(r"adopting"),
        "detect and discuss",
        "survey and memo",
        "baseline",
        "scaffold",
        "adopt modules",
        "legacy check",
        "outline-approved",
        "setup",
        "app-accepted",
    )


def test_adoption_memo_describes_the_app_as_it_is() -> None:
    has_all(
        section(r"adopting"),
        "as it is",
        "legacy files:",
        "legacy tests:",
        "callers to repoint:",
        "## legacy code",
        "app shell:",
        "app shell tests:",
        "legacy folders:",
        "renames:",
    )


def test_adoption_legacy_code_stays_until_replaced_and_gates_scope() -> None:
    has_all(
        section(r"adopting"),
        "legacy code stays",
        "bull gates <m>",
        "journeys",
        "build and pass its tests",
    )


def test_adoption_briefs_carry_adopt_unit_and_legacy_files() -> None:
    has_all(
        section(r"adopting"),
        "adopt: unit",
        "legacy files",
        "code-writer may read them",
        "test-writer never does",
    )


def test_adoption_switch_over_steps_in_order() -> None:
    in_order(
        section(r"adopting"),
        "switch-over",
        "bull status next",
        "legacy-test-scanner",
        "mode: adopt",
        "contradicts",
        "not-in-spec",
        "missed",
        "adopt: legacy cases",
        "bull status unit <m> <n> tests",
        "adopt: switch-over",
        "callers",
        "legacy files",
        "bull gates <m> --fast",
        "bull status unit <m> <n> code",
        "scope: switch-over <m>",
        "bull status unit <m> <n> done",
    )


def test_adoption_features_wait_and_it_is_for_one_part_apps() -> None:
    has_all(
        section(r"adopting"),
        "queued during an adoption",
        "after it finishes",
        "one-part",
    )


# --- handing off and never ---------------------------------------------------------------


def test_handing_off_points_at_resume_in_a_fresh_session() -> None:
    has_all(
        section(r"handing off"),
        "fresh session",
        "/bull:resume",
        "memo",
        "bull status",
        "git log",
    )


@pytest.mark.parametrize(
    "terms",
    [
        ("extra usage", "api key", "pay-as-you-go"),
        ("delete branches", "reset", "force-push"),
        ("start a feature", "app-accepted", "adoption"),
        ("improvise gates", "bull stacks"),
        ("edit tests to make code pass", "code to make tests pass"),
        ("mark anything", "passed its gates"),
        ("hand-edit", ".bull/status.json", ".bull/backlog.json"),
    ],
)
def test_never_section_lists_the_prohibition(terms: tuple[str, ...]) -> None:
    has_all(section(r"^never"), *terms)
