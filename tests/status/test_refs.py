"""Tests for `bull.Modules.status.refs`: branch and tag names per mode."""

from __future__ import annotations

from dataclasses import replace

import pytest

from bull.Modules.settings.mocks import MockSettings
from bull.Modules.status.Contracts import StatusError
from bull.Modules.status.mocks import MockStatusStore, sample_status
from bull.Modules.status.refs import LiveRefs


def make(
    mode: str = "app", trunk: str | None = None
) -> tuple[LiveRefs, MockStatusStore, MockSettings]:
    settings = MockSettings()
    if trunk is not None:
        settings.app["base_branch"] = trunk
    store = MockStatusStore(sample_status())
    if mode == "feature":
        store.start_feature("dark-mode")
    elif mode == "adopt":
        store.start_adoption()
    return LiveRefs(settings, store), store, settings


def test_trunk_is_the_base_branch_setting() -> None:
    refs, _, _ = make(trunk="develop")
    assert refs.trunk() == "develop"


def test_trunk_defaults_to_main() -> None:
    refs, _, _ = make()
    assert refs.trunk() == "main"


@pytest.mark.parametrize("mode", ["app", "feature", "adopt"])
def test_trunk_is_the_same_in_every_mode(mode: str) -> None:
    refs, _, _ = make(mode, trunk="develop")
    assert refs.trunk() == "develop"


def test_base_in_app_mode_is_the_trunk() -> None:
    refs, _, _ = make(trunk="develop")
    assert refs.base() == "develop"


def test_base_in_feature_mode_is_the_feature_main() -> None:
    refs, _, _ = make("feature")
    assert refs.base() == "feature/dark-mode/main"


def test_base_in_adopt_mode_is_adopt_main() -> None:
    refs, _, _ = make("adopt")
    assert refs.base() == "adopt/main"


def test_module_branch_in_app_mode_has_no_prefix() -> None:
    refs, _, _ = make()
    assert refs.module_branch("Counter") == "module/Counter"


def test_module_branch_in_feature_mode_has_the_feature_prefix() -> None:
    refs, _, _ = make("feature")
    assert refs.module_branch("Counter") == "feature/dark-mode/module/Counter"


def test_module_branch_in_adopt_mode_has_the_adopt_prefix() -> None:
    refs, _, _ = make("adopt")
    assert refs.module_branch("Counter") == "adopt/module/Counter"


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("app", "skeleton"),
        ("feature", "feature/dark-mode/skeleton"),
        ("adopt", "adopt/skeleton"),
    ],
)
def test_tag_gets_the_mode_prefix(mode: str, expected: str) -> None:
    refs, _, _ = make(mode)
    assert refs.tag("skeleton") == expected


@pytest.mark.parametrize("mode", ["app", "feature", "adopt"])
def test_adopted_tag_is_never_prefixed(mode: str) -> None:
    refs, _, _ = make(mode)
    assert refs.tag("adopted") == "adopted"


def test_tag_for_a_module_label_is_prefixed_in_feature_mode() -> None:
    refs, _, _ = make("feature")
    assert refs.tag("module/Store") == "feature/dark-mode/module/Store"


def test_adoption_wins_over_feature_for_the_prefix() -> None:
    refs, store, _ = make("adopt")
    store.status = replace(
        store.status, feature=MockStatusStore().start_feature("x").feature
    )
    assert refs.base() == "adopt/main"


def test_feature_slug_follows_the_store() -> None:
    refs, store, _ = make("feature")
    store.end_feature()
    store.start_feature("other")
    assert refs.base() == "feature/other/main"


def test_module_for_branch_in_app_mode() -> None:
    refs, _, _ = make()
    assert refs.module_for_branch("module/Counter") == "Counter"


@pytest.mark.parametrize(
    "branch",
    [
        "main",
        "feature/dark-mode/module/Counter",
        "adopt/module/Counter",
        "feature/dark-mode/main",
        "",
    ],
)
def test_module_for_branch_in_app_mode_ignores_other_branches(branch: str) -> None:
    refs, _, _ = make()
    assert refs.module_for_branch(branch) is None


def test_module_for_branch_in_feature_mode() -> None:
    refs, _, _ = make("feature")
    assert refs.module_for_branch("feature/dark-mode/module/Counter") == "Counter"


@pytest.mark.parametrize(
    "branch",
    [
        "module/Counter",
        "feature/other/module/Counter",
        "adopt/module/Counter",
        "feature/dark-mode/main",
        "main",
    ],
)
def test_module_for_branch_in_feature_mode_ignores_other_branches(branch: str) -> None:
    refs, _, _ = make("feature")
    assert refs.module_for_branch(branch) is None


def test_module_for_branch_in_adopt_mode() -> None:
    refs, _, _ = make("adopt")
    assert refs.module_for_branch("adopt/module/Counter") == "Counter"


@pytest.mark.parametrize(
    "branch",
    ["module/Counter", "feature/dark-mode/module/Counter", "adopt/main", "main"],
)
def test_module_for_branch_in_adopt_mode_ignores_other_branches(branch: str) -> None:
    refs, _, _ = make("adopt")
    assert refs.module_for_branch(branch) is None


# --- coverage triage: other modes' branches, bad branch names, base_branch guard ----------


@pytest.mark.parametrize("branch", ["module/Counter", "main", "adopt/module/Counter"])
def test_module_for_branch_in_feature_mode_is_none_for_a_branch_of_another_mode(
    branch: str,
) -> None:
    refs, _, _ = make("feature")
    assert refs.module_for_branch(branch) is None


@pytest.mark.parametrize("branch", ["module/", "module/Counter/extra"])
def test_module_for_branch_without_a_single_module_name_is_none(branch: str) -> None:
    refs, _, _ = make()
    assert refs.module_for_branch(branch) is None


@pytest.mark.parametrize("value", ["", 5, True])
def test_trunk_refuses_an_empty_or_non_string_base_branch(value: object) -> None:
    refs, _, settings = make()
    settings.app["base_branch"] = value  # type: ignore[assignment]
    with pytest.raises(StatusError) as caught:
        refs.trunk()
    assert "base_branch" in caught.value.message
