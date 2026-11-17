"""Content of commands/adopt.md, resume.md, status.md and stack.md."""

from __future__ import annotations

import re

import pytest

from bull.Modules.plugin_text.plugin_files import LivePluginText


def _norm(text: str) -> str:
    """Lower-case, backticks dropped, whitespace collapsed."""
    return re.sub(r"\s+", " ", text.replace("`", "")).strip().lower()


def _raw(name: str) -> str:
    path = f"commands/{name}.md"
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


def in_order(name: str, *terms: str) -> None:
    norm = _norm(_body(name))
    pos = 0
    for t in terms:
        found = norm.find(t.lower(), pos)
        assert found >= 0, f"{name}: {t!r} missing or out of order (after {pos})"
        pos = found + len(t)


def tag_of(checkpoint: str) -> str:
    return f"git tag $(bull status ref tag {checkpoint})"


# --- frontmatter -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "description"),
    [
        (
            "adopt",
            (
                "Adopt an existing app — bring an app built outside bull under it, "
                "stage by stage, until every part is a tested module"
            ),
        ),
        ("resume", "Resume the pipeline after a pause or in a fresh session"),
        ("status", "Show pipeline progress and plan usage"),
        (
            "stack",
            (
                "Build a stack (a language or platform bull can build apps with) "
                "in its own stack repo, stage by stage"
            ),
        ),
    ],
)
def test_description_matches_the_note(name: str, description: str) -> None:
    assert _norm(_frontmatter(name)["description"]).startswith(_norm(description))


def test_adopt_argument_hint_says_it_continues_an_adoption_in_progress() -> None:
    hint = _frontmatter("adopt").get("argument-hint", "").lower()
    assert "nothing" in hint
    assert "continues an adoption in progress" in hint


def test_stack_argument_hint_says_it_continues_the_stack_in_this_repo() -> None:
    hint = _frontmatter("stack").get("argument-hint", "").lower()
    assert "nothing" in hint
    assert "continues the stack in this repo" in hint


# --- adopt: general ----------------------------------------------------------------------


def test_adopt_intro_says_one_part_apps_and_new_work_through_feature() -> None:
    has_all("adopt", "/bull:feature", "until nothing legacy is left")


def test_adopt_checks_usage_before_every_step_and_commits_after_every_step() -> None:
    has_all("adopt", "bull status usage-check", "commit after every step")


def test_adopt_takes_refs_from_status_ref_and_keeps_work_in_files() -> None:
    has_all(
        "adopt",
        "bull status ref",
        "adopt/",
        "docs/discussion-notes.md",
        "docs/adopt/",
    )


# --- adopt: stage 0 ----------------------------------------------------------------------


def test_adopt_stage_0_asks_where_we_are_with_status_next() -> None:
    has_all("adopt", "0.", "bull status next")


def test_adopt_stage_0_stops_for_an_app_already_built_by_bull() -> None:
    has_all("adopt", "app-accepted", "not for it")


def test_adopt_stage_0_mentions_init_adopt_having_detected_and_started() -> None:
    has_all("adopt", "bull init --adopt")


# --- adopt: stage 1 ----------------------------------------------------------------------


def test_adopt_stage_1_runs_stack_detect_and_handles_each_issue_kind() -> None:
    has_all("adopt", "bull stack detect", "block", "fix", "note")


def test_adopt_stage_1_applies_detected_settings_then_commits() -> None:
    in_order(
        "adopt",
        "bull stack detect --apply",
        "chore: adopt: detected project settings",
    )


def test_adopt_stage_1_starts_the_adoption_with_adopt_start() -> None:
    has_all("adopt", "bull adopt start")


def test_adopt_start_comes_after_apply() -> None:
    in_order("adopt", "bull stack detect --apply", "bull adopt start")


def test_adopt_never_tells_the_agent_to_switch_to_adopt_main_by_hand() -> None:
    assert "git switch -c adopt/main" not in _norm(_body("adopt"))


def test_adopt_stage_1_saves_detection_to_docs_adopt_detection_md() -> None:
    has_all("adopt", "docs/adopt/detection.md")


def test_adopt_stage_1_discusses_the_app_as_it_exists() -> None:
    has_all(
        "adopt",
        "journeys",
        "known bugs",
        "bull feature add",
        "out of scope",
    )


def test_adopt_stage_1_ends_by_setting_stage_2() -> None:
    in_order("adopt", "bull adopt start", "bull status stage 2")


# --- adopt: stage 2 ----------------------------------------------------------------------


def test_adopt_stage_2_inventory_comes_from_adopt_legacy_into_inventory_md() -> None:
    has_all("adopt", "bull adopt legacy", "docs/adopt/inventory.md")


def test_adopt_never_names_a_stack_inventory_command() -> None:
    assert "bull stack inventory" not in _norm(_body("adopt"))


def test_adopt_stage_2_plans_surveyor_passes_of_about_15_files_or_3000_lines() -> None:
    has_all("adopt", "surveyor", "15 files", "3,000 lines")


def test_adopt_stage_2_pass_kinds_cover_screens_data_services_tests_modules() -> None:
    has_all("adopt", "screens", "data", "services", "tests", "module <name>")


def test_adopt_stage_2_gauge_lists_survey_passes() -> None:
    has_all("adopt", "bull status plan survey")


def test_adopt_stage_2_saves_each_pass_as_survey_file() -> None:
    has_all("adopt", "docs/adopt/survey-<pass>.md")


def test_adopt_stage_2_partial_pass_gets_a_follow_up_for_not_read() -> None:
    has_all("adopt", "partial", "not read")


def test_adopt_stage_2_memo_comes_from_template_and_stack_outline_rules() -> None:
    has_all("adopt", "bull template outline", "bull stack rules outline")


def test_adopt_stage_2_memo_has_the_adoption_lines() -> None:
    has_all(
        "adopt",
        "legacy files:",
        "legacy tests:",
        "callers to repoint:",
        "## legacy code",
        "app shell:",
        "app shell tests:",
        "legacy folders:",
        "renames:",
        "## known issues",
    )


def test_adopt_stage_2_readiness_list_uses_check_and_cross_marks() -> None:
    has_all("adopt", "✅", "❌")


def test_adopt_stage_2_init_modules_then_outline_approved_checkpoint_and_tag() -> None:
    in_order(
        "adopt",
        "bull status init-modules",
        "bull status checkpoint outline-approved",
        "docs: adoption outline approved",
        tag_of("outline-approved"),
    )


# --- adopt: setup ------------------------------------------------------------------------


def test_adopt_setup_checks_then_walks_the_adoption_section() -> None:
    in_order(
        "adopt",
        "bull stack check",
        'bull stack setup --section "for an adoption"',
    )


def test_adopt_setup_commits_then_records_setup_checkpoint_and_tag() -> None:
    in_order(
        "adopt",
        "bull status checkpoint setup",
        "chore: adopt setup",
        tag_of("setup"),
    )


# --- adopt: stage 3 ----------------------------------------------------------------------


def test_adopt_stage_3_sets_stage_and_gauge_items_in_order() -> None:
    in_order(
        "adopt",
        "bull status stage 3",
        "bull status plan baseline",
        "clean-launch",
        "identifiers",
        "journeys",
        "fixes",
        "old-tests",
        "hands-on",
    )


def test_adopt_stage_3_code_writer_uses_adopt_baseline() -> None:
    has_all("adopt", "adopt: baseline", "test: adopt: clean-state launch")


def test_adopt_stage_3_identifiers_use_screen_builder_adopt_identifiers() -> None:
    has_all("adopt", "screen-builder", "mode: adopt-identifiers")


def test_adopt_stage_3_journeys_use_journey_test_writer_adopt_baseline() -> None:
    has_all(
        "adopt",
        "journey-test-writer",
        "mode: adopt-baseline",
        "bull gates --journeys",
    )


def test_adopt_stage_3_fixes_record_known_issues_fixed_in_baseline() -> None:
    has_all("adopt", "fixed in baseline", "max_attempts")


def test_adopt_stage_3_old_tests_run_gates_without_coverage_then_all() -> None:
    in_order(
        "adopt",
        "bull gates --all --skip-coverage",
        "fix code",
        "disable",
        "delete",
        "bull gates --all",
    )


def test_adopt_stage_3_ends_with_baseline_checkpoint_and_tag() -> None:
    in_order("adopt", "hands-on", "bull status checkpoint baseline", tag_of("baseline"))


# --- adopt: stage 4 ----------------------------------------------------------------------


def test_adopt_stage_4_sets_stage_four() -> None:
    has_all("adopt", "bull status stage 4")


def test_adopt_stage_4_rename_step_comes_before_scaffold_step() -> None:
    in_order("adopt", "skeleton-builder", "step: rename", "step: scaffold")


def test_adopt_stage_4_uses_adopt_mode_and_rename_commit() -> None:
    has_all("adopt", "mode: adopt", "refactor: adopt: rename clashing legacy types")


def test_adopt_stage_4_writes_api_snapshots_and_commits_scaffold() -> None:
    in_order("adopt", "step: scaffold", "bull api", "--write", "chore: adopt: scaffold")


def test_adopt_stage_4_scaffold_checkpoint_then_tag() -> None:
    in_order(
        "adopt",
        "bull status checkpoint scaffold",
        "chore: adopt: scaffold",
        tag_of("scaffold"),
    )


# --- adopt: stage 5 ----------------------------------------------------------------------


def test_adopt_stage_5_sets_stage_five() -> None:
    has_all("adopt", "bull status stage 5")


def test_adopt_stage_5_stops_for_an_old_test_that_contradicts_the_spec() -> None:
    has_all("adopt", "contradicts")


def test_adopt_stage_5_human_merges_the_trunk_into_adopt_main() -> None:
    has_all("adopt", "git merge <trunk>", "terminal", "merge guard")


def test_adopt_stage_5_trunk_merge_is_followed_by_gates_all() -> None:
    in_order("adopt", "git merge <trunk>", "bull gates --all")


# --- adopt: stage 6 ----------------------------------------------------------------------


def test_adopt_stage_6_sets_stage_six_and_gauge() -> None:
    in_order(
        "adopt",
        "bull status stage 6",
        "bull status plan verify",
        "legacy-check",
        "final-switch",
        "app-review",
        "fixes",
        "hands-on",
        "backlog",
    )


def test_adopt_stage_6_legacy_check_expects_nothing_left_to_replace() -> None:
    in_order("adopt", "legacy-check", "bull adopt legacy", "nothing left to replace.")


def test_adopt_stage_6_final_switch_section_then_check_then_gates() -> None:
    in_order(
        "adopt",
        'bull stack setup --section "final switch"',
        "bull stack check",
        "bull gates --all",
    )


def test_adopt_stage_6_runs_journeys() -> None:
    has_all("adopt", "bull gates --journeys")


def test_adopt_stage_6_cleans_the_memo_of_adoption_lines() -> None:
    has_all("adopt", "remove", "decisions-log")


def test_adopt_stage_6_finish_comes_before_the_merge_into_the_trunk() -> None:
    in_order(
        "adopt",
        "bull adopt finish",
        "chore: adoption finished",
        "bull gates --all",
        "git switch <trunk>",
        "git merge --no-ff adopt/main",
    )


def test_adopt_stage_6_adopted_tag_is_unprefixed_and_after_the_merge() -> None:
    in_order("adopt", "git merge --no-ff adopt/main", "git tag adopted")


def test_adopt_stage_6_adopted_tag_does_not_use_status_ref() -> None:
    assert tag_of("adopted") not in _norm(_body("adopt"))


def test_adopt_stage_6_backlog_lists_features() -> None:
    in_order("adopt", "git tag adopted", "bull feature list", "/bull:feature")


# --- adopt: abandoning -------------------------------------------------------------------


def test_adopt_abandon_only_when_the_human_says_so() -> None:
    has_all("adopt", "abandon", "only when the human says so")


def test_adopt_abandon_switches_to_trunk_then_runs_adopt_abandon() -> None:
    in_order("adopt", "abandoning", "git switch <trunk>", "bull adopt abandon")


def test_adopt_abandon_leaves_trunk_untouched_and_keeps_branches() -> None:
    has_all("adopt", "trunk untouched", "adopt/*", "queued features")


# --- resume ------------------------------------------------------------------------------


def test_resume_reads_status_and_recent_log_first() -> None:
    in_order("resume", "bull status", "git log --oneline -15")


def test_resume_reads_the_memo_build_order_and_trusts_files_over_memory() -> None:
    has_all("resume", "build order", "memory")


def test_resume_checks_usage_and_stops_on_pause() -> None:
    in_order("resume", "bull status usage-check", "pause", "stop")


def test_resume_stashes_uncommitted_changes_and_tells_the_human() -> None:
    has_all("resume", 'git stash push -m "interrupted step"', "human", "restart")


def test_resume_steps_are_in_the_fixed_order() -> None:
    in_order(
        "resume",
        "git log --oneline -15",
        "bull status usage-check",
        'git stash push -m "interrupted step"',
        "bull status resume",
        "bull status next",
    )


def test_resume_continues_the_feature_on_its_branch() -> None:
    has_all("resume", "feature", "/bull:feature", "branch")


def test_resume_continues_an_adoption_with_adopt_on_adopt_main() -> None:
    has_all("resume", "/bull:adopt", "adopt/main")


def test_resume_takes_a_contract_approval_wait_to_the_human_first() -> None:
    has_all("resume", "approval", "human first")


def test_resume_sends_a_stack_repo_to_the_stack_command() -> None:
    has_all("resume", "stack", "/bull:stack")


# --- status ------------------------------------------------------------------------------


def test_status_runs_bull_status_and_usage_check() -> None:
    has_all("status", "bull status", "bull status usage-check")


def test_status_report_lines_cover_stage_modules_next_step_blocked_usage() -> None:
    has_all(
        "status",
        "stage",
        "modules done",
        "next step",
        "blocked",
        "approval",
        "plan usage",
    )


def test_status_has_a_line_for_feature_adoption_and_backlog() -> None:
    has_all("status", "feature", "adoption", "backlog", "bull feature list")


def test_status_in_a_stack_repo_reports_stage_checkpoints_and_next_step() -> None:
    has_all("status", "stack repo", "checkpoints")


# --- stack: refusal and rules ------------------------------------------------------------


def test_stack_refuses_outside_a_stack_repo_naming_init_and_open() -> None:
    has_all("stack", "bull init --stack", "bull open", "stack repo")


def test_stack_refusal_is_the_first_step() -> None:
    in_order("stack", "bull status", "bull init --stack", "bull open")


def test_stack_checks_usage_before_every_step_and_commits_after() -> None:
    has_all("stack", "bull status usage-check", "commit after every step")


def test_stack_stages_and_checkpoints_go_through_bull_status() -> None:
    has_all("stack", "bull status stage", "bull status checkpoint", "bull status next")


def test_stack_tags_use_status_ref_tag() -> None:
    has_all("stack", "git tag $(bull status ref tag")


def test_stack_briefs_use_mode_stack_without_module_or_unit_lines() -> None:
    has_all("stack", "mode: stack", "no module or unit")


def test_stack_briefs_point_at_the_stack_files_section_of_this_command() -> None:
    has_all("stack", ".bull/plugin/commands/stack.md", "stack files", "design.md")


# --- stack: stages -----------------------------------------------------------------------


def test_stack_stage_1_settles_every_design_heading() -> None:
    has_all(
        "stack",
        "design.md",
        "language and tools",
        "contracts",
        "modules",
        "kind",
        "human setup",
        "adoption support",
        "interfaces and running",
        "decisions log",
    )


def test_stack_stage_1_waits_for_approval_then_design_checkpoint_and_tag() -> None:
    in_order(
        "stack",
        "✋",
        "bull status checkpoint design-approved",
        tag_of("design-approved"),
    )


def test_stack_stage_2_scaffold_fills_stack_toml_and_creates_skeletons() -> None:
    in_order(
        "stack",
        "bull status stage 2",
        "stack.toml",
        "todo",
        "experimental",
        "readers.py",
        "rules.md",
        "setup.md",
    )


def test_stack_stage_3_test_writer_writes_fixture_and_cases() -> None:
    in_order(
        "stack",
        "bull status stage 3",
        "test-writer",
        "mode: stack",
        "fixture/",
        "cases.json",
    )


def test_stack_static_check_runs_before_the_real_test() -> None:
    in_order("stack", "bull stack test . --static", "bull stack test .")


def test_stack_stage_4_code_writer_writes_gate_program_and_readers() -> None:
    in_order(
        "stack",
        "bull status stage 4",
        "code-writer",
        "mode: stack",
        "readers.py",
        "setup.md",
    )


def test_stack_stage_4_needs_a_static_pass_and_not_run_fails() -> None:
    has_all("stack", "static pass", "not run")


def test_stack_stage_5_writes_rules_and_reviews_with_scope_stack() -> None:
    in_order(
        "stack",
        "bull status stage 5",
        "rules.md",
        "reviewer",
        "scope: stack",
    )


def test_stack_stage_5_rules_headings_are_listed() -> None:
    has_all("stack", "## common", "## outline", "one ## <agent>")


def test_stack_stage_5_human_reviews_rules_then_rules_checkpoint_and_tag() -> None:
    in_order(
        "stack",
        "scope: stack",
        "✋",
        "bull status checkpoint rules-approved",
        tag_of("rules-approved"),
    )


def test_stack_stage_6_runs_full_test_then_accepted_checkpoint_and_tag() -> None:
    in_order(
        "stack",
        "bull status stage 6",
        "bull stack test .",
        "bull status checkpoint accepted",
        tag_of("accepted"),
    )


def test_stack_stage_6_tells_the_human_about_install_and_maturity() -> None:
    in_order(
        "stack",
        "bull status checkpoint accepted",
        "bull stack install",
        "experimental",
        "verified",
    )


# --- stack: Stack files section ----------------------------------------------------------


def _stack_files() -> str:
    norm = _norm(_body("stack"))
    idx = norm.find("stack files")
    assert idx >= 0, "no Stack files section"
    # the section proper is the last occurrence (earlier ones are references)
    return norm[norm.rfind("stack files") :]


def _stack_files_has(*terms: str) -> None:
    section = _stack_files()
    missing = [t for t in terms if t.lower() not in section]
    assert not missing, f"Stack files: missing {missing}"


def test_stack_files_section_exists_with_the_folder_contents() -> None:
    _stack_files_has(
        "stack.toml", "readers.py", "rules.md", "setup.md", "design.md", "cases.json"
    )
    _stack_files_has("fixture/")


def test_stack_files_names_every_stack_table_and_key() -> None:
    _stack_files_has(
        "[stack]",
        "name",
        "title",
        "description",
        "language",
        "kind",
        "maturity",
        "source_glob",
        "test_glob",
        "comment",
        "scaffold",
        "gitignore",
        "agents",
        "[[stack.requires]]",
        "[settings.<key>]",
        "source_dir",
        "test_dir",
        "[run]",
        "[interfaces]",
        "[commands]",
    )


def test_stack_files_names_every_gate_key() -> None:
    _stack_files_has(
        "[gates]",
        "preflight",
        "setup",
        "build_test",
        "build_test_fast",
        "lint",
        "rerun_failed",
        "journeys",
    )


def test_stack_files_describes_placeholders_environment_and_exit_codes() -> None:
    _stack_files_has("placeholders", "bull_", "exit 0", "bull-fail:", "exit 2")


def test_stack_files_names_the_four_required_reader_functions() -> None:
    _stack_files_has("contract_declarations", "test_results", "uncovered", "check")


def test_stack_files_names_the_optional_reader_functions() -> None:
    _stack_files_has("detect", "inventory", "legacy_declarations", "interface_check")


def test_stack_files_names_rules_headings() -> None:
    _stack_files_has("## common", "## <agent>", "## outline")


def test_stack_files_names_setup_sections() -> None:
    _stack_files_has("## for a feature", "## for an adoption", "## final switch")


def test_stack_files_names_the_cases_json_fields() -> None:
    _stack_files_has(
        "format",
        "layout",
        "settings",
        "cases",
        "id",
        "change",
        "add",
        "replace",
        "delete",
        "run",
        "expect",
        "verdict",
        "gate",
        "output",
        "recorded",
        "ran",
        "then",
    )


@pytest.mark.parametrize(
    "case_id",
    [
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
    ],
)
def test_stack_files_lists_each_required_case_id(case_id: str) -> None:
    assert case_id in _stack_files()


@pytest.mark.parametrize(
    ("case_id", "condition"),
    [
        ("journey", "journeys"),
        ("journey-failing", "journeys"),
        ("interface-drift", "interfaces"),
        ("run-lifecycle", "[run]"),
        ("adopt-mode", "detect"),
    ],
)
def test_stack_files_lists_each_conditional_case_id_with_its_condition(
    case_id: str, condition: str
) -> None:
    section = _stack_files()
    assert case_id in section
    assert condition in section


@pytest.mark.parametrize(
    "agent",
    [
        "skeleton-builder",
        "test-writer",
        "code-writer",
        "reviewer",
        "coverage-analyst",
        "journey-test-writer",
        "surveyor",
    ],
)
def test_stack_files_lists_each_agent(agent: str) -> None:
    assert agent in _stack_files()


# --- stack: neutral wording --------------------------------------------------------------


def test_stack_text_names_no_language() -> None:
    norm = _norm(_body("stack"))
    banned = [
        "swift",
        "python",
        "xcode",
        "kotlin",
        "java",
        "rust",
        "ruby",
        "android",
        "pytest",
        "cargo",
        "gradle",
        "ios",
    ]
    norm = norm.replace("{python}", " ").replace("readers.py", " ")
    found = [w for w in banned if re.search(rf"\b{w}\b", norm)]
    assert not found, f"stack.md names a language or platform: {found}"
