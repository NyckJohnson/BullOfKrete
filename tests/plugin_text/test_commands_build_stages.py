"""Content of commands/prototype.md, build.md, verify.md and feature.md."""

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


TAG_UI = "git tag $(bull status ref tag ui-approved)"
NEGATION = re.compile(r"\b(not|never|don't|do not|skip|without|except|no)\b")


def sentences(name: str) -> list[str]:
    return [x for x in re.split(r"(?<=[.;:!?])\s", _norm(_body(name))) if x]


def negated(name: str, word: str) -> bool:
    """Some sentence says `word` together with a negation."""
    return any(word in x and NEGATION.search(x) for x in sentences(name))


# --- frontmatter -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "description"),
    [
        (
            "prototype",
            "Stage 4 — build the UI on mocks for the human to try (checkpoint 2)",
        ),
        ("build", "Stage 5 — build modules one at a time, foundational first"),
        ("verify", "Stage 6 — test and verify the full app (checkpoint 4)"),
        (
            "feature",
            (
                "Add features after the app is accepted — queue ideas (one, or a "
                "file of them) and build them one at a time"
            ),
        ),
    ],
)
def test_description_matches_the_note(name: str, description: str) -> None:
    assert _norm(_frontmatter(name)["description"]).startswith(_norm(description))


def test_build_argument_hint_names_the_single_module_option() -> None:
    hint = _frontmatter("build").get("argument-hint", "")
    assert "module name to build only that one" in hint.lower()


def test_feature_argument_hint_names_idea_file_or_nothing() -> None:
    hint = _frontmatter("feature").get("argument-hint", "").lower()
    assert "idea" in hint
    assert "path to a backlog file" in hint
    assert "nothing to continue" in hint


# --- prototype ---------------------------------------------------------------------------


def test_prototype_sets_stage_four() -> None:
    assert "bull status stage 4" in _norm(_body("prototype"))


def test_prototype_gauge_lists_one_item_per_screen() -> None:
    has_all("prototype", "bull status plan prototype", "<screen>")


def test_prototype_gauge_is_set_before_the_first_screen_is_built() -> None:
    in_order("prototype", "bull status plan prototype", "screen-builder")


def test_prototype_checks_usage_per_screen() -> None:
    has_all("prototype", "bull status usage-check", "per screen")


def test_prototype_screen_builder_brief_names_part_entry_journeys_protocols_mocks() -> (
    None
):
    has_all(
        "prototype",
        "screen-builder",
        "part:",
        "memo entry",
        "journeys",
        "protocols",
        "mocks",
    )


def test_prototype_runs_gates_without_coverage_and_fixes_through_the_same_agent() -> (
    None
):
    has_all(
        "prototype",
        "bull gates --all --skip-coverage",
        "same agent",
        "max_attempts",
    )


def test_prototype_screen_gates_come_before_the_commit() -> None:
    in_order(
        "prototype",
        "screen-builder",
        "bull gates --all --skip-coverage",
        "feat(ui): <screen> prototype",
    )


def test_prototype_ticks_the_screen_before_its_commit() -> None:
    in_order("prototype", "bull status tick", "feat(ui): <screen> prototype")


def test_prototype_human_tries_every_journey() -> None:
    has_all("prototype", "every journey", "previews")


def test_prototype_screen_or_flow_feedback_goes_to_screen_builder_and_memo() -> None:
    has_all("prototype", "feedback", "screens section", "screen-builder")


def test_prototype_protocol_change_is_checkpoint_three() -> None:
    has_all(
        "prototype",
        "protocol change",
        "checkpoint 3",
        "reason",
        "affected modules",
        "approval",
    )


def test_prototype_protocol_change_updates_the_memo_first() -> None:
    has_all("prototype", "memo first")


def test_prototype_approval_checkpoint_comes_before_the_approval_commit() -> None:
    in_order(
        "prototype",
        "bull status checkpoint ui-approved",
        "chore: prototype approved",
    )


def test_prototype_tags_ui_approved_after_the_status_change() -> None:
    in_order("prototype", "bull status checkpoint ui-approved", TAG_UI)


def test_prototype_tags_through_status_ref_in_both_paths() -> None:
    norm = _norm(_body("prototype"))
    assert norm.count(TAG_UI) >= 2


def test_prototype_never_uses_a_bare_ui_approved_tag() -> None:
    assert "git tag ui-approved" not in _norm(_raw("prototype"))


def test_prototype_clears_the_gauge_at_the_end() -> None:
    has_all("prototype", "bull status plan prototype --clear")


def test_prototype_clear_comes_after_the_tick() -> None:
    in_order("prototype", "bull status tick", "--clear")


def test_prototype_hands_off_to_build() -> None:
    in_order("prototype", "bull status checkpoint ui-approved", "/bull:build")


def test_prototype_no_screens_path_says_so_and_asks_for_ok() -> None:
    has_all("prototype", "no screens", "decisions log")


def test_prototype_no_screens_path_records_the_checkpoint_and_tag() -> None:
    norm = _norm(_body("prototype"))
    start = norm.find("no screens")
    assert start >= 0
    tail = norm[start:]
    assert "bull status checkpoint ui-approved" in tail
    assert TAG_UI in tail
    assert tail.find("bull status checkpoint ui-approved") < tail.find(TAG_UI)


# --- build -------------------------------------------------------------------------------


def test_build_sets_stage_five() -> None:
    assert "bull status stage 5" in _norm(_body("build"))


def test_build_stage_during_a_feature_is_the_features() -> None:
    has_all("build", "feature", "bull status ref")


def test_build_picks_the_next_module_or_the_argument() -> None:
    has_all("build", "bull status next", "$arguments")


def test_build_follows_the_stage_five_loop_with_usage_check_before_each_step() -> None:
    has_all("build", "stage 5 loop", "bull status usage-check", "before every step")


def test_build_uses_fast_gates_while_iterating_and_failed_reruns() -> None:
    has_all("build", "--fast", "--failed", "iterating")


def test_build_only_the_full_gates_record_the_pass() -> None:
    has_all("build", "bull gates <m>", "records")


def test_build_runs_after_merge_gates_following_a_merge() -> None:
    has_all("build", "--after-merge")


def test_build_runs_all_gates_once_after_the_last_module() -> None:
    has_all("build", "bull gates --all", "last module")


def test_build_all_modules_done_hands_off_to_verify() -> None:
    has_all("build", "all modules", "done", "/bull:verify")


def test_build_in_a_feature_or_adoption_continues_with_their_stage_six() -> None:
    has_all("build", "/bull:feature", "/bull:adopt", "stage 6")


def test_build_stops_on_pause_and_pauses() -> None:
    has_all("build", "bull status pause")


def test_build_stops_and_asks_on_blocked_unit_contract_change_or_findings() -> None:
    has_all(
        "build",
        "blocked unit",
        "contract change",
        "reference-scan",
        "coverage finding",
        "ask",
    )


def test_build_adoption_last_unit_is_the_switch_over() -> None:
    has_all("build", "adoption", "switch-over", "adopt:")


def test_build_reports_at_module_boundaries_one_short_line() -> None:
    has_all("build", "module boundaries", "one short line per module")


# --- verify ------------------------------------------------------------------------------


def test_verify_sets_stage_six() -> None:
    assert "bull status stage 6" in _norm(_body("verify"))


def test_verify_gauge_has_every_item() -> None:
    has_all(
        "verify",
        "bull status plan verify",
        "mocks-check",
        "<one item per journey>",
        "app-review",
        "fixes",
        "hands-on",
        "backlog",
    )


def test_verify_gauge_items_are_in_the_notes_order() -> None:
    in_order(
        "verify",
        "bull status plan verify",
        "mocks-check",
        "app-review",
        "fixes",
        "hands-on",
        "backlog",
    )


def test_verify_mirrors_the_gauge_as_a_task_list_and_ticks_each() -> None:
    has_all("verify", "task list", "bull status tick")


def test_verify_clears_the_gauge_at_the_end() -> None:
    has_all("verify", "bull status plan verify --clear")


def test_verify_mocks_check_wants_real_implementations_outside_tests_and_previews() -> (
    None
):
    has_all("verify", "real implementations", "mocks only in tests and previews")


def test_verify_journey_test_writer_writes_one_test_per_journey() -> None:
    has_all("verify", "journey-test-writer", "one journey test per memo journey")


def test_verify_with_parts_briefs_one_writer_per_part_with_part_line() -> None:
    has_all("verify", "one brief per part", "part:")


def test_verify_runs_journey_gates_after_the_writer() -> None:
    in_order("verify", "journey-test-writer", "bull gates --journeys")


def test_verify_checks_usage_before_the_writer_and_the_reviewer() -> None:
    has_all("verify", "bull status usage-check")


def test_verify_reviewer_reads_the_whole_app() -> None:
    has_all("verify", "reviewer", "scope: whole app", "consistency across modules")


def test_verify_whole_app_review_comes_after_the_journey_tests() -> None:
    in_order("verify", "bull gates --journeys", "scope: whole app")


def test_verify_whole_app_review_with_parts_lists_every_part() -> None:
    has_all("verify", "every part")


def test_verify_routes_failures_to_the_owning_modules_stage_five_loop() -> None:
    has_all("verify", "owning module", "stage 5 loop")


def test_verify_wrong_design_proposes_a_memo_change_first() -> None:
    has_all("verify", "design is wrong", "memo change first")


def test_verify_hands_on_walks_every_journey_with_a_numbered_list() -> None:
    has_all("verify", "hands-on", "every journey", "numbered list")


def test_verify_hands_on_items_are_fix_now_later_or_drop() -> None:
    has_all("verify", "fix now", "later", "drop")


def test_verify_later_items_are_queued_with_feature_add() -> None:
    has_all("verify", 'bull feature add "<title>: <what they said>"')


def test_verify_retests_fixes_and_asks_for_acceptance() -> None:
    has_all("verify", "retest", "accept")


def test_verify_acceptance_checkpoint_comes_before_the_tag() -> None:
    in_order(
        "verify",
        "bull status checkpoint app-accepted",
        "git tag app-accepted",
    )


def test_verify_acceptance_is_committed() -> None:
    has_all("verify", "chore: app accepted")


def test_verify_says_a_feature_takes_acceptance_and_next_step_from_feature() -> None:
    norm = _norm(_body("verify"))
    assert "/bull:feature" in norm
    assert any(
        "feature" in x and "acceptance" in x and "/bull:feature" in x
        for x in sentences("verify")
    )


def test_verify_backlog_previews_both_sections_with_dry_run() -> None:
    has_all(
        "verify",
        'bull feature import docs/outline.md --section "later features" --dry-run',
        '--section "out of scope"',
    )


def test_verify_backlog_shows_two_lists_plus_what_hands_on_queued() -> None:
    has_all("verify", "two short lists")


def test_verify_backlog_asks_which_to_queue_and_in_what_order() -> None:
    has_all("verify", "which to queue", "order")


def test_verify_backlog_queues_with_feature_add_and_top() -> None:
    has_all("verify", "bull feature add", "--top")


def test_verify_backlog_reorders_with_feature_move() -> None:
    has_all("verify", "bull feature move <slug> <pos>")


def test_verify_backlog_import_has_no_only_flag() -> None:
    assert "--only" not in _norm(_raw("verify"))


def test_verify_queue_changes_come_before_the_backlog_commit() -> None:
    in_order(
        "verify",
        "bull feature move",
        "docs: queue features after first release",
    )


def test_verify_lists_the_queue_after_committing() -> None:
    in_order(
        "verify",
        "docs: queue features after first release",
        "bull feature list",
    )


def test_verify_asks_whether_to_start_the_first_feature_now_or_later() -> None:
    has_all("verify", "/bull:feature", "fresh session", "now or later")


def test_verify_defers_to_adopt_and_feature_for_their_stage_six() -> None:
    has_all("verify", "/bull:adopt", "/bull:feature", "replaces")


def test_verify_says_hands_on_not_device_test() -> None:
    assert "device test" not in _norm(_raw("verify"))


# --- feature -----------------------------------------------------------------------------


def test_feature_follows_the_orchestrators_feature_cycle() -> None:
    has_all("feature", "feature cycle", "bull feature --help")


def test_feature_queue_step_reads_the_arguments() -> None:
    has_all("feature", "$arguments", "queue")


def test_feature_file_path_is_previewed_with_dry_run_before_import() -> None:
    has_all("feature", "bull feature import <path> --dry-run", "on ok")


def test_feature_import_without_dry_run_comes_after_the_preview() -> None:
    in_order("feature", "bull feature import <path> --dry-run", "without --dry-run")


def test_feature_nothing_found_shows_the_backlog_template() -> None:
    has_all("feature", "nothing found", "bull template backlog")


def test_feature_idea_in_words_is_queued_with_feature_add() -> None:
    has_all("feature", 'bull feature add "<title>: <one line>"')


def test_feature_top_only_when_the_human_says_so() -> None:
    has_all("feature", "--top", "only if the human says so")


def test_feature_no_arguments_skips_to_deciding() -> None:
    has_all("feature", "nothing", "step 2")


def test_feature_queued_ideas_are_committed_on_the_current_branch() -> None:
    has_all("feature", "docs: queue feature <slug>", "current branch")


def test_feature_queue_comes_before_the_queue_commit() -> None:
    in_order(
        "feature",
        "bull feature add",
        "docs: queue feature <slug>",
    )


def test_feature_decide_step_reads_status_next() -> None:
    has_all("feature", "bull status next")


def test_feature_active_feature_continues_at_its_stage_switching_branch_first() -> None:
    has_all("feature", "active feature", "switch branch")


def test_feature_not_accepted_or_adoption_active_leaves_ideas_queued_and_stops() -> (
    None
):
    has_all("feature", "not accepted", "adoption", "stay queued", "stop")


def test_feature_no_active_feature_lists_and_confirms_which() -> None:
    has_all("feature", "bull feature list", "first queued", "bull feature move")


def test_feature_start_commits_and_switches_by_itself() -> None:
    has_all(
        "feature",
        "bull feature start",
        "chore: start feature <slug>",
        "feature/<slug>/main",
    )


def test_feature_start_is_run_on_a_clean_trunk() -> None:
    has_all("feature", "clean trunk")


def test_feature_never_switches_with_git_switch_dash_c() -> None:
    assert "git switch -c feature/" not in _norm(_raw("feature"))


def test_feature_checks_usage_before_every_stage_step() -> None:
    has_all("feature", "bull status usage-check", "before every step")


def test_feature_status_stage_and_checkpoint_apply_to_the_feature() -> None:
    has_all("feature", "bull status stage", "bull status checkpoint")


def test_feature_tags_come_from_status_ref() -> None:
    has_all("feature", "git tag $(bull status ref tag <name>)")


def test_feature_stage_one_discusses_from_idea_and_records_agreed_scope() -> None:
    has_all(
        "feature",
        "idea",
        "discussion notes",
        "agreed scope",
        "failure paths",
        "contract changes",
        "out of scope",
    )


def test_feature_stage_two_edits_the_memo_in_place_with_numbered_journeys() -> None:
    has_all("feature", "in place", "next numbers")


def test_feature_stage_two_marks_changes_per_module() -> None:
    has_all("feature", "- changes (<slug>): <files>")


def test_feature_stage_two_new_files_go_in_a_new_unit() -> None:
    has_all("feature", "new unit", "| <file>", "files:", "never into a finished unit")


def test_feature_stage_two_marks_contract_changes() -> None:
    has_all("feature", "- contract changes (<slug>): <what>")


def test_feature_stage_two_adds_a_decisions_log_line() -> None:
    has_all("feature", "decisions-log line")


def test_feature_stage_two_removes_the_item_from_later_features_or_out_of_scope() -> (
    None
):
    has_all("feature", "later features", "out of scope", "remove")


def test_feature_stage_two_shows_the_memo_diff_against_the_trunk() -> None:
    has_all(
        "feature",
        "git diff <trunk> -- docs/outline.md",
        "bull status ref trunk",
    )


def test_feature_stage_two_approval_approves_the_contract_changes() -> None:
    has_all("feature", "approval approves those contract changes")


def test_feature_plan_runs_after_approval_and_its_output_is_checked() -> None:
    has_all("feature", "bull feature plan", "its output")


def test_feature_stage_two_order_is_plan_then_checkpoint_then_commit() -> None:
    in_order(
        "feature",
        "bull feature plan",
        "bull status checkpoint outline-approved",
        "docs: feature <slug> outline approved",
    )


def test_feature_stage_three_setup_only_if_needed() -> None:
    has_all(
        "feature",
        'bull stack setup --section "for a feature"',
        "bull stack check",
        "chore(<slug>): project setup",
    )


def test_feature_adding_a_part_runs_part_add_and_that_parts_whole_setup() -> None:
    has_all("feature", "bull part add", "whole setup")


def test_feature_skeleton_only_when_plan_says_skeleton_needed() -> None:
    has_all(
        "feature", "skeleton needed: yes", "skeleton-builder", "mode: feature <slug>"
    )


def test_feature_skeleton_gates_then_api_snapshots_then_commit() -> None:
    in_order(
        "feature",
        "bull gates --all --skip-coverage",
        "bull api <m> --write",
        "bull status checkpoint skeleton",
        "chore(<slug>): skeleton",
    )


def test_feature_skeleton_listed_contract_change_passes_once_as_pre_approved() -> None:
    has_all("feature", "pre-approved")


def test_feature_prototype_only_when_screens_are_new_or_changed() -> None:
    has_all("feature", "/bull:prototype", "stubs", "mocks")


def test_feature_unchanged_screens_record_the_checkpoint_with_a_note() -> None:
    has_all(
        "feature", "bull status checkpoint ui-approved", "nothing changed on screen"
    )


def test_feature_build_stage_marks_reopened_units_with_change_slug() -> None:
    has_all("feature", "stage 5 loop", "change: <slug>")


def test_feature_verify_uses_feature_modes_and_scopes() -> None:
    has_all(
        "feature",
        "/bull:verify",
        "journey-test-writer",
        "mode: feature <slug>",
        "bull gates --journeys",
        "scope: feature <slug>",
    )


def test_feature_acceptance_records_accepted_before_feature_accept() -> None:
    in_order(
        "feature",
        "bull status checkpoint accepted",
        "bull feature accept",
    )


def test_feature_acceptance_adds_the_feature_to_the_memos_features_section() -> None:
    has_all("feature", "docs: feature <slug> accepted", "features", "section")
    in_order("feature", "bull feature accept", "docs: feature <slug> accepted")


def test_feature_acceptance_runs_all_gates_on_the_feature_branch_then_merges() -> None:
    in_order(
        "feature",
        "bull feature accept",
        "bull gates --all",
        "git switch <trunk>",
        "git merge --no-ff feature/<slug>/main",
    )


def test_feature_accepted_tag_comes_after_the_merge() -> None:
    in_order(
        "feature",
        "git merge --no-ff feature/<slug>/main",
        "git tag feature/<slug>/accepted",
    )


def test_feature_stopping_points_and_fresh_session_suggestion() -> None:
    has_all(
        "feature",
        "pause",
        "blocked unit",
        "unlisted contract change",
        "fresh session",
        "/bull:resume",
    )


def test_feature_after_acceptance_names_the_next_queued_feature() -> None:
    has_all("feature", "next queued feature", "ask whether to start")


def test_feature_abandon_only_when_the_human_says_so() -> None:
    has_all("feature", "abandon", "only when the human says so")


def test_feature_abandon_switches_to_trunk_then_abandons() -> None:
    in_order("feature", "git switch <trunk>", "bull feature abandon")


def test_feature_abandon_leaves_trunk_untouched_and_carries_queued_ideas() -> None:
    has_all("feature", "untouched", "carried over")


def test_feature_verify_runs_the_checks_from_mocks_check_through_hands_on() -> None:
    has_all("feature", "/bull:verify", "mocks-check", "hands-on")
    in_order("feature", "mocks-check", "hands-on")


def test_feature_verify_does_not_run_verifys_acceptance() -> None:
    assert negated("feature", "acceptance")
    assert negated("feature", "app-accepted")


def test_feature_verify_does_not_run_verifys_backlog_step() -> None:
    assert negated("feature", "backlog")


def test_feature_never_tags_app_accepted() -> None:
    assert "git tag app-accepted" not in _norm(_raw("feature"))


def test_feature_accepted_tag_is_written_out_because_ref_has_no_prefix_any_more() -> (
    None
):
    norm = _norm(_body("feature"))
    i = norm.find("git tag feature/<slug>/accepted")
    assert i >= 0
    window = norm[max(0, i - 400) : i + 400]
    assert "ref" in window
    assert "ended" in window or "no longer" in window


def test_feature_no_setup_needed_puts_the_note_in_the_commit_message() -> None:
    norm = _norm(_body("feature"))
    assert re.search(r"chore\(<slug>\):[^.]*no setup", norm)


def test_feature_no_skeleton_needed_puts_the_note_in_the_commit_message() -> None:
    norm = _norm(_body("feature"))
    assert re.search(r"chore\(<slug>\):[^.]*no skeleton", norm)
