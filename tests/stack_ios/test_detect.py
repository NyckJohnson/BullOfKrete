"""Tests for `bull.Modules.stack_ios.ios.detect` (and readers.detect's pass-through)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from bull.Modules.stack_ios.ios import detect as detect_mod
from bull.Modules.stack_ios.ios import readers
from bull.Modules.stacks.Contracts import Detection, Issue, IssueLevel

from ._pbx_sample import APP, _render, make_project

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


# --- reference scan: actor isolation, Objective-C, UIKit, -uiTesting, Swift file count -------

APP_DIR = "App/MyApp/MyApp"
ISOLATION = '"SWIFT_DEFAULT_ACTOR_ISOLATION" = "{}"; '


def _set_isolation(proj: Path, cfg: str, value: str) -> None:
    head = (
        f'"{cfg}" = {{ "isa" = "XCBuildConfiguration"; "name" = "Debug"; '
        '"buildSettings" = { '
    )
    _edit_pbxproj(proj, head, head + ISOLATION.format(value))


def _swift(root: Path, name: str, body: str, folder: str = APP_DIR) -> None:
    path = root / folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _is_isolation(i: Issue) -> bool:
    return "isolation" in _text(i).lower()


@pytest.mark.parametrize("cfg", ["CFG_app", "CFG_unit", "CFG_project"])
def test_main_actor_default_isolation_gives_a_fix_mentioning_nonisolated(
    tmp_path: Path, cfg: str
) -> None:
    proj = make_project(tmp_path)
    _set_isolation(proj, cfg, "MainActor")
    d = detect_mod.detect(tmp_path)
    found = [i for i in _issues(d, IssueLevel.FIX) if _is_isolation(i)]
    assert found
    assert any("nonisolated" in _text(i) for i in found)
    assert d.confidence >= HIGH


@pytest.mark.parametrize("value", ["nonisolated", None])
def test_nonisolated_or_unset_default_isolation_gives_no_isolation_issue(
    tmp_path: Path, value: str | None
) -> None:
    proj = make_project(tmp_path)
    if value:
        _set_isolation(proj, "CFG_app", value)
    d = detect_mod.detect(tmp_path)
    assert not any(_is_isolation(i) for i in d.issues)


@pytest.mark.parametrize("ext", ["m", "mm"])
def test_objective_c_sources_give_a_block_naming_objective_c(
    tmp_path: Path, ext: str
) -> None:
    make_project(tmp_path)
    _swift(tmp_path, f"Legacy.{ext}", "@implementation X\n@end\n")
    d = detect_mod.detect(tmp_path)
    blocks = _issues(d, IssueLevel.BLOCK)
    assert any("objective-c" in _text(i).lower() for i in blocks)
    assert d.confidence >= HIGH


def test_a_swift_only_app_has_no_objective_c_issue(tmp_path: Path) -> None:
    make_project(tmp_path)
    d = detect_mod.detect(tmp_path)
    assert not any("objective-c" in _text(i).lower() for i in d.issues)


@pytest.mark.parametrize("folder", ["Pods/Lib", "build/out", "App/MyApp/Pods/Lib"])
def test_objective_c_under_pods_or_build_folders_is_ignored(
    tmp_path: Path, folder: str
) -> None:
    make_project(tmp_path)
    _swift(tmp_path, "Lib.m", "@end\n", folder=folder)
    d = detect_mod.detect(tmp_path)
    assert not any("objective-c" in _text(i).lower() for i in d.issues)


def test_swift_files_importing_uikit_give_a_note_with_a_count(tmp_path: Path) -> None:
    make_project(tmp_path)
    for n in ("A", "B", "C"):
        _swift(tmp_path, f"{n}.swift", "import UIKit\nstruct X {}\n")
    _swift(tmp_path, "D.swift", "import SwiftUI\n")
    d = detect_mod.detect(tmp_path)
    notes = [i for i in _issues(d, IssueLevel.NOTE) if "UIKit" in _text(i)]
    assert notes
    assert any("3" in _text(i) for i in notes)


def test_no_uikit_imports_give_no_uikit_note(tmp_path: Path) -> None:
    make_project(tmp_path)
    _swift(tmp_path, "A.swift", "import SwiftUI\n")
    d = detect_mod.detect(tmp_path)
    assert not any("UIKit" in _text(i) for i in d.issues)


def test_no_ui_testing_launch_argument_gives_a_note(tmp_path: Path) -> None:
    make_project(tmp_path)
    _swift(tmp_path, "A.swift", "import SwiftUI\n")
    d = detect_mod.detect(tmp_path)
    assert any("-uiTesting" in _text(i) for i in _issues(d, IssueLevel.NOTE))


@pytest.mark.parametrize(
    "body",
    [
        'let on = CommandLine.arguments.contains("-uiTesting")\n',
        'let flag = "-uiTesting"\n',
    ],
)
def test_a_handled_ui_testing_launch_argument_gives_no_note(
    tmp_path: Path, body: str
) -> None:
    make_project(tmp_path)
    _swift(tmp_path, "Launch.swift", body)
    d = detect_mod.detect(tmp_path)
    assert not any("-uiTesting" in _text(i) for i in d.issues)


@pytest.mark.parametrize("count", [0, 1, 4])
def test_summary_includes_the_swift_file_count(tmp_path: Path, count: int) -> None:
    make_project(tmp_path)
    (tmp_path / APP_DIR / "MyAppApp.swift").unlink()
    for n in range(count):
        _swift(tmp_path, f"F{n}.swift", "struct X {}\n")
    d = detect_mod.detect(tmp_path)
    assert str(count) in d.summary


def test_new_issues_keep_confidence_high_and_have_fixes(tmp_path: Path) -> None:
    proj = make_project(tmp_path)
    _set_isolation(proj, "CFG_app", "MainActor")
    _swift(tmp_path, "Legacy.m", "@end\n")
    _swift(tmp_path, "V.swift", "import UIKit\n")
    d = detect_mod.detect(tmp_path)
    assert d.confidence >= HIGH
    assert len(d.issues) >= 4
    for issue in d.issues:
        assert issue.item.strip()
        assert issue.fix.strip()


# --- coverage triage: project selection and unreadable structure --------------------------


def _raw_project(root: Path, objects: dict[str, Any]) -> Path:
    """Write `<root>/P.xcodeproj/project.pbxproj` holding exactly `objects` (rootObject ROOT)."""
    proj = root / "P.xcodeproj"
    proj.mkdir(parents=True)
    top = {
        "archiveVersion": "1",
        "objectVersion": "77",
        "objects": objects,
        "rootObject": "ROOT",
    }
    (proj / "project.pbxproj").write_text(
        "// !$*UTF8*$!\n" + _render(top) + "\n", encoding="utf-8"
    )
    return proj


def _sync_objects(
    groups: dict[str, dict[str, Any]], main_children: list[str]
) -> dict[str, Any]:
    objects: dict[str, Any] = {
        "SYNC": {
            "isa": "PBXFileSystemSynchronizedRootGroup",
            "path": "Feature",
            "sourceTree": "<group>",
        },
        "TARGET": {
            "isa": "PBXNativeTarget",
            "name": "P",
            "productType": APP,
            "fileSystemSynchronizedGroups": ["SYNC"],
        },
        "MAIN": {
            "isa": "PBXGroup",
            "children": main_children,
            "sourceTree": "<group>",
        },
        "ROOT": {"isa": "PBXProject", "mainGroup": "MAIN", "targets": ["TARGET"]},
    }
    objects.update(groups)
    return objects


def _group(
    path: str | None, children: list[str], tree: str = "<group>"
) -> dict[str, Any]:
    group: dict[str, Any] = {
        "isa": "PBXGroup",
        "children": children,
        "sourceTree": tree,
    }
    if path is not None:
        group["path"] = path
    return group


def test_several_projects_use_the_first_and_a_note_names_the_others(
    tmp_path: Path,
) -> None:
    make_project(tmp_path)
    make_project(tmp_path, where="Other", name="Zed")
    d = detect_mod.detect(tmp_path)
    assert d.settings["project"] == "Other/Zed.xcodeproj"
    notes = _issues(d, IssueLevel.NOTE)
    assert any(
        "Several" in i.item and "App/MyApp/MyApp.xcodeproj" in i.item for i in notes
    )


def test_objects_that_is_not_a_dictionary_gives_the_cant_be_read_block(
    tmp_path: Path,
) -> None:
    proj = make_project(tmp_path)
    (proj / "project.pbxproj").write_text(
        '{ "objects" = ( a, ); "rootObject" = "ROOT"; }', encoding="utf-8"
    )
    d = detect_mod.detect(tmp_path)
    blocks = _issues(d, IssueLevel.BLOCK)
    assert any("can't be read" in i.item for i in blocks)
    assert d.settings == {"project": "App/MyApp/MyApp.xcodeproj"}


def test_a_workspace_folder_without_contents_gives_no_issue(tmp_path: Path) -> None:
    make_project(tmp_path)
    (tmp_path / "App" / "MyApp" / "MyApp.xcworkspace").mkdir()
    d = detect_mod.detect(tmp_path)
    assert not _issues(d, IssueLevel.BLOCK)
    assert not _issues(d, IssueLevel.FIX)


def test_an_unreadable_workspace_file_gives_a_fix_with_a_restore_from_git_hint(
    tmp_path: Path,
) -> None:
    make_project(tmp_path)
    ws = tmp_path / "App" / "MyApp" / "MyApp.xcworkspace"
    ws.mkdir()
    (ws / "contents.xcworkspacedata").write_bytes(b"\xff\xfe\x00\x80")
    fixes = _issues(detect_mod.detect(tmp_path), IssueLevel.FIX)
    hit = [i for i in fixes if "workspace" in i.item and "can't be read" in i.item]
    assert hit
    assert "git" in hit[0].fix


def test_workspace_entries_that_are_not_projects_are_ignored(tmp_path: Path) -> None:
    make_project(tmp_path)
    _workspace(tmp_path, ["MyApp.xcodeproj", "Scratch.playground", "Docs"])
    assert not _issues(detect_mod.detect(tmp_path), IssueLevel.BLOCK)


def test_an_absolute_workspace_location_of_another_project_blocks(
    tmp_path: Path,
) -> None:
    make_project(tmp_path)
    ws = tmp_path / "App" / "MyApp" / "MyApp.xcworkspace"
    ws.mkdir()
    extra = tmp_path / "Elsewhere" / "Extra.xcodeproj"
    (ws / "contents.xcworkspacedata").write_text(
        f'<Workspace><FileRef location = "absolute:{extra}"></FileRef></Workspace>',
        encoding="utf-8",
    )
    blocks = _issues(detect_mod.detect(tmp_path), IssueLevel.BLOCK)
    assert any("Extra.xcodeproj" in _text(i) for i in blocks)


def test_an_absolute_workspace_location_of_the_app_project_does_not_block(
    tmp_path: Path,
) -> None:
    proj = make_project(tmp_path)
    ws = tmp_path / "App" / "MyApp" / "MyApp.xcworkspace"
    ws.mkdir()
    (ws / "contents.xcworkspacedata").write_text(
        f'<Workspace><FileRef location = "absolute:{proj}"></FileRef></Workspace>',
        encoding="utf-8",
    )
    assert not _issues(detect_mod.detect(tmp_path), IssueLevel.BLOCK)


def test_nested_groups_are_joined_above_a_synchronized_group(tmp_path: Path) -> None:
    objects = _sync_objects(
        {"G1": _group("App", ["G2"]), "G2": _group("Sub", ["SYNC"])}, ["G1"]
    )
    _raw_project(tmp_path, objects)
    assert detect_mod.detect(tmp_path).settings["source_dir"] == "App/Sub/Feature"


def test_a_parent_group_without_a_path_is_skipped_when_joining(tmp_path: Path) -> None:
    objects = _sync_objects(
        {"G1": _group("App", ["G2"]), "G2": _group(None, ["SYNC"])}, ["G1"]
    )
    _raw_project(tmp_path, objects)
    assert detect_mod.detect(tmp_path).settings["source_dir"] == "App/Feature"


def test_a_parent_with_another_source_tree_stops_the_walk(tmp_path: Path) -> None:
    objects = _sync_objects(
        {
            "G1": _group("App", ["G2"]),
            "G2": _group("Sub", ["SYNC"], tree="SOURCE_ROOT"),
        },
        ["G1"],
    )
    _raw_project(tmp_path, objects)
    assert detect_mod.detect(tmp_path).settings["source_dir"] == "Sub/Feature"


def test_a_cycle_of_parent_groups_stops_without_hanging(tmp_path: Path) -> None:
    objects = _sync_objects(
        {"G1": _group("App", ["G2"]), "G2": _group("Sub", ["SYNC", "G1"])}, []
    )
    _raw_project(tmp_path, objects)
    assert detect_mod.detect(tmp_path).settings["source_dir"].endswith("Feature")


def test_a_main_group_without_children_does_not_crash(tmp_path: Path) -> None:
    objects = _sync_objects({}, [])
    del objects["MAIN"]["children"]
    del objects["TARGET"]["fileSystemSynchronizedGroups"]
    _raw_project(tmp_path, objects)
    d = detect_mod.detect(tmp_path)
    assert d.confidence >= HIGH
    assert any("group" in i.item for i in _issues(d, IssueLevel.FIX))


def test_a_project_without_any_target_has_no_swift_version_issue(
    tmp_path: Path,
) -> None:
    objects = {
        "MAIN": _group(None, []),
        "ROOT": {"isa": "PBXProject", "mainGroup": "MAIN", "targets": []},
    }
    _raw_project(tmp_path, objects)
    d = detect_mod.detect(tmp_path)
    assert _issues(d, IssueLevel.BLOCK)
    assert not any("Swift" in i.item and "ersion" in i.item for i in d.issues)
    assert not any("Swift 5" in i.item for i in d.issues)


@pytest.mark.parametrize(
    ("swift", "words"),
    [("4.2", "too old"), (None, "not set")],
)
def test_a_swift_version_below_5_or_unset_gives_a_fix(
    tmp_path: Path, swift: str | None, words: str
) -> None:
    make_project(tmp_path, swift=swift)
    fixes = _issues(detect_mod.detect(tmp_path), IssueLevel.FIX)
    assert any(words in i.item for i in fixes)


def test_an_unreadable_swift_path_counts_as_neither_uikit_nor_ui_testing(
    tmp_path: Path,
) -> None:
    make_project(tmp_path)
    (tmp_path / "App/MyApp/MyApp/Broken.swift").symlink_to(tmp_path / "nowhere.swift")
    d = detect_mod.detect(tmp_path)
    assert d.confidence >= HIGH
    assert not any("UIKit" in i.item for i in d.issues)
    assert any("-uiTesting" in i.item for i in _issues(d, IssueLevel.NOTE))
