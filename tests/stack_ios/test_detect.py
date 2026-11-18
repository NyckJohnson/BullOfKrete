"""Tests for `bull.Modules.stack_ios.ios.detect` (and readers.detect's pass-through)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from bull.Modules.stack_ios.ios import detect as detect_mod
from bull.Modules.stack_ios.ios import readers
from bull.Modules.stacks.Contracts import Detection, Issue, IssueLevel

from ._pbx_sample import make_project

HIGH = 0.8
LOW = 0.2


def _issues(d: Detection, level: IssueLevel) -> list[Issue]:
    return [i for i in d.issues if i.level == level]


def _text(issue: Issue) -> str:
    return f"{issue.item} {issue.fix}"


def test_no_xcodeproj_gives_low_confidence_summary_and_no_settings(
    tmp_path: Path,
) -> None:
    (tmp_path / "README.md").write_text("hello", encoding="utf-8")
    d = detect_mod.detect(tmp_path)
    assert d.confidence <= LOW
    assert d.summary.strip()
    assert not d.settings


def test_project_found_gives_high_confidence(tmp_path: Path) -> None:
    make_project(tmp_path)
    d = detect_mod.detect(tmp_path)
    assert d.confidence >= HIGH
    assert d.summary.strip()


def test_proposes_settings_relative_to_root(tmp_path: Path) -> None:
    make_project(tmp_path)
    s = detect_mod.detect(tmp_path).settings
    assert s["project"] == "App/MyApp/MyApp.xcodeproj"
    assert s["scheme"] == "MyApp"
    assert s["source_dir"] == "App/MyApp/MyApp"
    assert s["test_dir"] == "App/MyApp/MyAppTests"
    assert s["ui_test_dir"] == "App/MyApp/MyAppUITests"
    assert s["unit_test_target"] == "MyAppTests"
    assert s["ui_test_target"] == "MyAppUITests"


def test_project_at_the_root_gives_paths_without_a_prefix(tmp_path: Path) -> None:
    make_project(tmp_path, where=".", name="Solo")
    s = detect_mod.detect(tmp_path).settings
    assert s["project"] == "Solo.xcodeproj"
    assert s["source_dir"] == "Solo"
    assert s["test_dir"] == "SoloTests"
    assert s["ui_test_dir"] == "SoloUITests"


def test_test_targets_are_told_apart_by_product_type_not_name(tmp_path: Path) -> None:
    proj = make_project(tmp_path)
    pbx = proj / "project.pbxproj"
    text = pbx.read_text(encoding="utf-8")
    text = text.replace("MyAppUITests", "Zeta").replace("MyAppTests", "Alpha")
    pbx.write_text(text, encoding="utf-8")
    s = detect_mod.detect(tmp_path).settings
    assert s["unit_test_target"] == "Alpha"
    assert s["ui_test_target"] == "Zeta"
    assert s["test_dir"].endswith("/Alpha")
    assert s["ui_test_dir"].endswith("/Zeta")


def test_a_clean_project_has_no_block_or_fix_issues(tmp_path: Path) -> None:
    make_project(tmp_path)
    d = detect_mod.detect(tmp_path)
    assert not _issues(d, IssueLevel.BLOCK)
    assert not _issues(d, IssueLevel.FIX)


def test_swift_5_app_is_reported_as_note_or_fix_not_block(tmp_path: Path) -> None:
    make_project(tmp_path, swift="5.0")
    d = detect_mod.detect(tmp_path)
    assert d.confidence >= HIGH
    found = [i for i in d.issues if "Swift 5" in _text(i)]
    assert found
    assert all(i.level in (IssueLevel.NOTE, IssueLevel.FIX) for i in found)
    assert not _issues(d, IssueLevel.BLOCK)


def test_swift_version_falls_back_to_the_project_setting(tmp_path: Path) -> None:
    make_project(tmp_path, swift=None, project_swift="5.0")
    d = detect_mod.detect(tmp_path)
    assert any("Swift 5" in _text(i) for i in d.issues)


def test_swift_6_raises_no_swift_5_issue(tmp_path: Path) -> None:
    make_project(tmp_path, swift="6.0")
    d = detect_mod.detect(tmp_path)
    assert not any("Swift 5" in _text(i) for i in d.issues)


def test_groups_give_a_fix_naming_the_group_and_convert_to_folder(
    tmp_path: Path,
) -> None:
    make_project(tmp_path, sync=False)
    d = detect_mod.detect(tmp_path)
    fixes = _issues(d, IssueLevel.FIX)
    assert any("MyApp" in i.item and "Convert to Folder" in i.fix for i in fixes)
    assert d.settings["source_dir"] == "App/MyApp/MyApp"


def test_missing_unit_test_target_gives_a_fix_naming_the_xcode_step(
    tmp_path: Path,
) -> None:
    make_project(tmp_path, unit=False)
    d = detect_mod.detect(tmp_path)
    fixes = [i for i in _issues(d, IssueLevel.FIX) if "Unit Testing Bundle" in i.fix]
    assert fixes
    assert not any("UI Testing Bundle" in i.fix for i in _issues(d, IssueLevel.FIX))


def test_missing_ui_test_target_gives_a_fix_naming_the_xcode_step(
    tmp_path: Path,
) -> None:
    make_project(tmp_path, ui=False)
    d = detect_mod.detect(tmp_path)
    fixes = [i for i in _issues(d, IssueLevel.FIX) if "UI Testing Bundle" in i.fix]
    assert fixes
    assert not any("Unit Testing Bundle" in i.fix for i in _issues(d, IssueLevel.FIX))


def test_no_shared_scheme_gives_a_fix(tmp_path: Path) -> None:
    make_project(tmp_path, shared_scheme=False)
    d = detect_mod.detect(tmp_path)
    assert any("scheme" in _text(i).lower() for i in _issues(d, IssueLevel.FIX))


def test_podfile_blocks(tmp_path: Path) -> None:
    make_project(tmp_path)
    (tmp_path / "Podfile").write_text("pod 'Alamofire'\n", encoding="utf-8")
    blocks = _issues(detect_mod.detect(tmp_path), IssueLevel.BLOCK)
    assert any("Podfile" in _text(i) for i in blocks)


def test_cartfile_blocks(tmp_path: Path) -> None:
    make_project(tmp_path)
    (tmp_path / "Cartfile").write_text('github "a/b"\n', encoding="utf-8")
    blocks = _issues(detect_mod.detect(tmp_path), IssueLevel.BLOCK)
    assert any("Cartfile" in _text(i) for i in blocks)


def _workspace(root: Path, refs: list[str]) -> None:
    ws = root / "App" / "MyApp" / "MyApp.xcworkspace"
    ws.mkdir(parents=True)
    body = "".join(f'<FileRef location = "group:{r}"></FileRef>' for r in refs)
    (ws / "contents.xcworkspacedata").write_text(
        f'<?xml version="1.0"?><Workspace version = "1.0">{body}</Workspace>',
        encoding="utf-8",
    )


def test_workspace_listing_extra_projects_blocks(tmp_path: Path) -> None:
    make_project(tmp_path)
    _workspace(tmp_path, ["MyApp.xcodeproj", "Pods/Pods.xcodeproj"])
    blocks = _issues(detect_mod.detect(tmp_path), IssueLevel.BLOCK)
    assert any("Pods" in _text(i) or "workspace" in _text(i).lower() for i in blocks)


def test_workspace_listing_only_the_app_project_does_not_block(tmp_path: Path) -> None:
    make_project(tmp_path)
    _workspace(tmp_path, ["MyApp.xcodeproj"])
    assert not _issues(detect_mod.detect(tmp_path), IssueLevel.BLOCK)


def test_swift_package_dependencies_do_not_block(tmp_path: Path) -> None:
    make_project(tmp_path, spm=True)
    d = detect_mod.detect(tmp_path)
    assert not _issues(d, IssueLevel.BLOCK)
    assert d.confidence >= HIGH


@pytest.mark.parametrize(
    "content", ["{ unbalanced", "", "not a plist at all", "{ a = ; }"]
)
def test_malformed_pbxproj_gives_a_block_or_fix_issue_not_an_exception(
    tmp_path: Path, content: str
) -> None:
    proj = make_project(tmp_path)
    (proj / "project.pbxproj").write_text(content, encoding="utf-8")
    d = detect_mod.detect(tmp_path)
    assert any(i.level in (IssueLevel.BLOCK, IssueLevel.FIX) for i in d.issues)


@pytest.mark.parametrize(
    "options",
    [
        {"swift": "5.0"},
        {"sync": False},
        {"unit": False},
        {"ui": False},
        {"shared_scheme": False},
    ],
)
def test_every_issue_has_a_non_empty_fix(
    tmp_path: Path, options: dict[str, Any]
) -> None:
    make_project(tmp_path, **options)
    (tmp_path / "Podfile").write_text("", encoding="utf-8")
    d = detect_mod.detect(tmp_path)
    assert d.issues
    for issue in d.issues:
        assert issue.item.strip()
        assert issue.fix.strip()


def test_readers_detect_returns_what_detect_returns(tmp_path: Path) -> None:
    make_project(tmp_path)
    assert readers.detect(tmp_path) == detect_mod.detect(tmp_path)


def _edit_pbxproj(proj: Path, old: str, new: str) -> None:
    pbx = proj / "project.pbxproj"
    text = pbx.read_text(encoding="utf-8")
    assert old in text
    pbx.write_text(text.replace(old, new), encoding="utf-8")


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ('"rootObject" = "ROOT";', '"rootObject" = ( a, );'),
        ('"rootObject" = "ROOT";', '"rootObject" = { a = b; };'),
        ('"mainGroup" = "MAIN";', '"mainGroup" = ( x, );'),
        ('"mainGroup" = "MAIN";', '"mainGroup" = { a = b; };'),
    ],
)
def test_odd_root_or_main_group_structure_gives_a_block_not_an_exception(
    tmp_path: Path, old: str, new: str
) -> None:
    proj = make_project(tmp_path)
    _edit_pbxproj(proj, old, new)
    d = detect_mod.detect(tmp_path)
    assert _issues(d, IssueLevel.BLOCK)
    assert d.confidence >= HIGH


@pytest.mark.parametrize(
    "content", ["{ unbalanced", "", "not a plist at all", "{ a = ; }"]
)
def test_malformed_pbxproj_still_reports_high_confidence_with_a_block(
    tmp_path: Path, content: str
) -> None:
    proj = make_project(tmp_path)
    (proj / "project.pbxproj").write_text(content, encoding="utf-8")
    d = detect_mod.detect(tmp_path)
    assert d.confidence >= HIGH
    assert _issues(d, IssueLevel.BLOCK)


def test_unreadable_pbxproj_still_reports_high_confidence_with_a_block(
    tmp_path: Path,
) -> None:
    proj = make_project(tmp_path)
    (proj / "project.pbxproj").write_bytes(b"\xff\xfe\x00\x80 not utf-8 \xc3\x28")
    d = detect_mod.detect(tmp_path)
    assert d.confidence >= HIGH
    assert _issues(d, IssueLevel.BLOCK)


def test_project_without_an_app_target_reports_high_confidence_with_a_block(
    tmp_path: Path,
) -> None:
    proj = make_project(tmp_path)
    _edit_pbxproj(
        proj,
        '"productType" = "com.apple.product-type.application";',
        '"productType" = "com.apple.product-type.framework";',
    )
    d = detect_mod.detect(tmp_path)
    assert d.confidence >= HIGH
    assert _issues(d, IssueLevel.BLOCK)


def _add_schemes(proj: Path, names: list[str], *, drop: str | None = None) -> None:
    schemes = proj / "xcshareddata" / "xcschemes"
    schemes.mkdir(parents=True, exist_ok=True)
    if drop:
        (schemes / f"{drop}.xcscheme").unlink()
    for n in names:
        (schemes / f"{n}.xcscheme").write_text("<Scheme/>\n", encoding="utf-8")


def test_several_shared_schemes_choose_the_one_named_after_the_app_target(
    tmp_path: Path,
) -> None:
    proj = make_project(tmp_path)
    _add_schemes(proj, ["Aardvark", "Zebra"])
    assert detect_mod.detect(tmp_path).settings["scheme"] == "MyApp"


def test_several_shared_schemes_with_no_app_match_choose_one_and_note_it(
    tmp_path: Path,
) -> None:
    proj = make_project(tmp_path)
    _add_schemes(proj, ["Beta", "Alpha"], drop="MyApp")
    d = detect_mod.detect(tmp_path)
    chosen = d.settings["scheme"]
    assert chosen in {"Alpha", "Beta"}
    notes = _issues(d, IssueLevel.NOTE)
    assert any(chosen in _text(i) and "scheme" in _text(i).lower() for i in notes)
