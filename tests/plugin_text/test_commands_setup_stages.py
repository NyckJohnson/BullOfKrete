"""Content of commands/discuss.md, outline.md, setup.md and skeleton.md."""

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


# --- frontmatter -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "description"),
    [
        (
            "discuss",
            "Stage 1 — discuss the app's purpose, stack, journeys and constraints",
        ),
        (
            "outline",
            "Stage 2 — write the outline memo and get it approved (checkpoint 1)",
        ),
        (
            "setup",
            (
                "Setup — walk the human through the stack's manual steps, then check "
                "them (between outline and skeleton)"
            ),
        ),
        ("skeleton", "Stage 3 — build the compiling skeleton"),
    ],
)
def test_description_matches_the_note(name: str, description: str) -> None:
    assert _norm(_frontmatter(name)["description"]).startswith(_norm(description))


def test_discuss_has_an_argument_hint_for_the_app_idea() -> None:
    hint = _frontmatter("discuss").get("argument-hint", "")
    assert "one-line app idea" in hint.lower()


# --- discuss -----------------------------------------------------------------------------


def test_discuss_sets_stage_one_first() -> None:
    in_order("discuss", "bull status stage 1")


def test_discuss_asks_one_or_two_questions_at_a_time_without_a_questionnaire() -> None:
    has_all("discuss", "one or two questions", "questionnaire")


def test_discuss_agrees_purpose_and_target_user() -> None:
    has_all("discuss", "purpose", "target user")


def test_discuss_lists_stacks_and_recommends_one() -> None:
    has_all("discuss", "bull stacks", "recommend")


def test_discuss_offers_only_listed_stacks_and_handles_experimental() -> None:
    has_all("discuss", "experimental", "verified")


def test_discuss_unlisted_stack_points_to_init_stack_and_the_stack_command() -> None:
    has_all("discuss", "bull init --stack", "/bull:stack")


def test_discuss_selects_the_stack_then_commits() -> None:
    in_order("discuss", "bull stack select", "chore: select")


def test_discuss_commit_message_names_the_stack() -> None:
    has_all("discuss", "chore: select <name> stack")


def test_discuss_adds_parts_when_stacks_differ() -> None:
    has_all("discuss", "bull part add", "--dir", "parts")


def test_discuss_parts_talk_through_interfaces() -> None:
    has_all("discuss", "interface", "file format")


def test_discuss_covers_journeys() -> None:
    has_all("discuss", "journeys", "failure paths", "end state")


def test_discuss_separates_mvp_from_later_features_and_never_drops_ideas() -> None:
    has_all("discuss", "mvp", "later features")


def test_discuss_covers_constraints() -> None:
    has_all("discuss", "constraints", "offline", "accounts", "sync")


def test_discuss_records_out_of_scope_with_reasons() -> None:
    has_all("discuss", "out of scope", "reason")


def test_discuss_keeps_running_notes_in_the_discussion_notes_file() -> None:
    has_all("discuss", "docs/discussion-notes.md", "commit")


def test_discuss_notes_have_the_headings_feature_import_reads() -> None:
    has_all(
        "discuss",
        "## stack",
        "## later features",
        "## out of scope",
        "bull feature import",
    )


def test_discuss_hands_off_to_outline() -> None:
    in_order("discuss", "bull status stage 1", "/bull:outline")


# --- outline -----------------------------------------------------------------------------


def test_outline_sets_stage_two_before_writing_the_memo() -> None:
    in_order("outline", "bull status stage 2", "docs/outline.md")


def test_outline_follows_the_template_and_the_stack_outline_rules() -> None:
    has_all("outline", "bull template outline", "bull stack rules outline")


def test_outline_without_a_stack_goes_back_to_discuss() -> None:
    has_all("outline", "bull config show", "discuss")


def test_outline_with_parts_uses_part_rules_and_part_lines() -> None:
    has_all("outline", "--part", "- parts:", "- part:", "## interfaces")


def test_outline_modules_are_folders_with_no_dependency_modules_first() -> None:
    has_all("outline", "folders", "dependenc")


def test_outline_splits_files_into_units_with_a_pipe() -> None:
    has_all("outline", "files:", "build order", "units", "max_files_per_unit")


def test_outline_puts_contracts_and_models_first() -> None:
    has_all("outline", "contracts", "models")


def test_outline_drafts_the_protocol_in_contracts() -> None:
    has_all("outline", "protocol", "contracts/")


def test_outline_lists_anticipated_operations() -> None:
    has_all("outline", "anticipated operations")


def test_outline_copies_later_features_and_out_of_scope_into_the_memo() -> None:
    has_all("outline", "later features", "out of scope")


def test_outline_covers_rewrite_of_an_existing_tool() -> None:
    has_all(
        "outline",
        "rewrite of an existing tool",
        "reference_dir",
        "reference tests:",
        "## unmapped reference tests",
        "reason",
    )


def test_outline_reports_a_readiness_list_with_check_and_cross_marks() -> None:
    has_all("outline", "readiness", "✅", "❌")


def test_outline_readiness_reads_screens_or_command_surface() -> None:
    has_all("outline", "screens (or command surface) and navigation")


def test_outline_revises_until_approved() -> None:
    has_all("outline", "revise", "approved")


def test_outline_init_modules_comes_before_the_checkpoint() -> None:
    in_order(
        "outline",
        "bull status init-modules",
        "bull status checkpoint outline-approved",
    )


def test_outline_init_modules_refusal_is_checked() -> None:
    has_all("outline", "init-modules", "line numbers")


def test_outline_status_changes_come_before_the_commit() -> None:
    in_order(
        "outline",
        "bull status init-modules",
        "bull status checkpoint outline-approved",
        "docs: outline approved",
    )


def test_outline_tags_outline_approved_after_the_commit() -> None:
    in_order("outline", "docs: outline approved", "git tag outline-approved")


def test_outline_hands_off_to_setup() -> None:
    in_order("outline", "bull status checkpoint outline-approved", "/bull:setup")


# --- setup -------------------------------------------------------------------------------


def test_setup_checks_usage_first() -> None:
    in_order("setup", "bull status usage-check", "bull stack check")


def test_setup_requires_the_approved_memo_else_back_to_outline() -> None:
    has_all("setup", "outline-approved", "bull status", "/bull:outline")


def test_setup_checks_every_part() -> None:
    has_all("setup", "bull stack check", "bull part check")


def test_setup_passing_check_skips_to_the_commit_step() -> None:
    has_all("setup", "passing", "step 5")


def test_setup_walks_the_stack_setup_guide_one_part_at_a_time() -> None:
    has_all("setup", "bull stack setup", "--part", "one part at a time")


def test_setup_goes_one_step_at_a_time_and_waits_for_done() -> None:
    has_all("setup", "one step at a time", "done", "memo")


def test_setup_skips_what_the_check_shows_done() -> None:
    has_all("setup", "skip")


def test_setup_confirms_settings_with_the_human_then_sets_them() -> None:
    in_order("setup", "confirm", "bull config set")
    has_all("setup", "--part")


def test_setup_rechecks_until_all_pass_and_explains_each_failure() -> None:
    has_all("setup", "re-check", "✅", "❌")


def test_setup_stops_when_a_failure_cannot_be_fixed() -> None:
    has_all("setup", "stop", "don't continue")


def test_setup_checkpoint_comes_before_the_commit() -> None:
    in_order("setup", "bull status checkpoint setup", "chore: project setup")


def test_setup_tags_setup_after_the_commit() -> None:
    in_order("setup", "chore: project setup", "git tag setup")


def test_setup_uses_a_neutral_manual_step_example() -> None:
    has_all("setup", "creating the project files the stack's tools need")


def test_setup_hands_off_to_skeleton() -> None:
    in_order("setup", "bull status checkpoint setup", "/bull:skeleton")


# --- skeleton ----------------------------------------------------------------------------


def test_skeleton_checks_usage_then_sets_stage_three() -> None:
    in_order("skeleton", "bull status usage-check", "bull status stage 3")


def test_skeleton_refused_without_setup_sends_the_human_to_setup() -> None:
    has_all("skeleton", "refused", "setup", "/bull:setup")


def test_skeleton_with_parts_runs_once_per_part_in_build_order() -> None:
    has_all("skeleton", "once per part", "build order", "part:")


def test_skeleton_builder_brief_points_at_memo_and_config() -> None:
    has_all(
        "skeleton",
        "skeleton-builder",
        "docs/outline.md",
        ".bull/config.toml",
        ".bull/parts/<part>.toml",
    )


def test_skeleton_brief_is_given_before_gates_run() -> None:
    in_order("skeleton", "skeleton-builder", "bull gates --all --skip-coverage")


def test_skeleton_manual_steps_are_walked_through_and_gates_rerun() -> None:
    has_all("skeleton", "manual steps for human", "rerun")


def test_skeleton_runs_gates_without_coverage_and_all_must_pass() -> None:
    has_all("skeleton", "bull gates --all --skip-coverage", "pass")


def test_skeleton_writes_api_snapshots_per_module_and_interface() -> None:
    has_all("skeleton", "bull api <m> --write", "bull api --interface <name> --write")


def test_skeleton_gates_come_before_the_api_snapshots() -> None:
    in_order(
        "skeleton",
        "bull gates --all --skip-coverage",
        "bull api <m> --write",
    )


def test_skeleton_interface_snapshots_come_after_gates() -> None:
    in_order(
        "skeleton",
        "bull gates --all --skip-coverage",
        "bull api --interface <name> --write",
    )


def test_skeleton_checkpoint_comes_before_the_commit() -> None:
    in_order(
        "skeleton",
        "bull api <m> --write",
        "bull status checkpoint skeleton",
        "chore: skeleton",
    )


def test_skeleton_tags_skeleton_after_the_commit() -> None:
    in_order("skeleton", "chore: skeleton", "git tag skeleton")


def test_skeleton_blocked_or_failing_gates_after_max_attempts_stops() -> None:
    has_all("skeleton", "blocked", "max_attempts", "stop")


def test_skeleton_hands_off_to_prototype() -> None:
    in_order("skeleton", "bull status checkpoint skeleton", "/bull:prototype")
