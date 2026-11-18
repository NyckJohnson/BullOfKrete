"""Tests for `bull.Modules.stack_ios.ios.readers`: what unit 2 covers.

`test_results`, `uncovered`, `detect` and `inventory` are pass-throughs tested with their own
modules (`xcresults`, `detect`, `inventory`); here: the module's shape, the declaration readers'
hand-off to `swift_scan`, and `check`.

Choices where the spec is open: `check` returns one item per probe, found by words in the item
text; the Xcode probe looks only for `xcodebuild` on PATH (no other subprocess); the scheme must
exist as a shared scheme file at `<project>/xcshareddata/xcschemes/<scheme>.xcscheme`; the Swift
language mode is the app and test targets' `SWIFT_VERSION` (target setting, else the project's);
a source or test folder counts as included when it is a synchronized root group
(`PBXFileSystemSynchronizedRootGroup`) listed in the owning target's
`fileSystemSynchronizedGroups`, the group's `path` being the folder's last path component;
a nested git repo is a `.git` entry in any folder below the part root; a `.pbxproj` that does
not parse becomes a failing item, not an exception.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from bull.Modules.stack_ios.ios import readers
from bull.Modules.stacks.Contracts import CheckItem

# --- module shape --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "contract_declarations",
        "test_results",
        "uncovered",
        "check",
        "detect",
        "inventory",
        "legacy_declarations",
    ],
)
def test_readers_define_the_function(name: str) -> None:
    assert callable(getattr(readers, name))


def test_readers_do_not_define_interface_check() -> None:
    assert not hasattr(readers, "interface_check")


# --- check: samples ------------------------------------------------------------------------

_SETTINGS = {
    "project": "App/MyApp/MyApp.xcodeproj",
    "scheme": "MyApp",
    "source_dir": "App/MyApp/MyApp",
    "test_dir": "App/MyApp/MyAppTests",
    "ui_test_dir": "App/MyApp/MyAppUITests",
    "unit_test_target": "MyAppTests",
    "ui_test_target": "MyAppUITests",
    "simulator": "",
}


def _pbxproj(
    *,
    swift_project: str = "6.0",
    swift_target: str | None = None,
    sync: tuple[str, ...] = ("app", "unit", "ui"),
    in_target: tuple[str, ...] = ("app", "unit", "ui"),
) -> str:
    """A project with an app, a unit test and a UI test target, each owning one folder.

    `sync` lists the folders made synchronized root groups (the rest are plain groups);
    `in_target` lists the targets that actually reference their folder.
    """
    folders = {
        "app": ("G1", "MyApp"),
        "unit": ("G2", "MyAppTests"),
        "ui": ("G3", "MyAppUITests"),
    }
    targets = {
        "app": ("T1", "MyApp"),
        "unit": ("T2", "MyAppTests"),
        "ui": ("T3", "MyAppUITests"),
    }
    out = ["// !$*UTF8*$!", "{", "\tobjects = {"]
    out.append(
        "\t\tP1 /* Project object */ = {\n\t\t\tisa = PBXProject;\n"
        "\t\t\tbuildConfigurationList = PCL;\n\t\t\tmainGroup = MG;\n"
        "\t\t\ttargets = (T1, T2, T3);\n\t\t};"
    )
    out.append(
        "\t\tPCL = { isa = XCConfigurationList; buildConfigurations = (PC); };\n"
        "\t\tPC = { isa = XCBuildConfiguration; name = Debug; buildSettings = {\n"
        f"\t\t\tSWIFT_VERSION = {swift_project};\n\t\t}}; }};"
    )
    out.append(
        '\t\tMG = { isa = PBXGroup; children = (G1, G2, G3); sourceTree = "<group>"; };'
    )
    for key, (gid, path) in folders.items():
        if key in sync:
            out.append(
                f"\t\t{gid} /* {path} */ = {{ isa = PBXFileSystemSynchronizedRootGroup; "
                f'path = {path}; sourceTree = "<group>"; }};'
            )
        else:
            out.append(
                f"\t\t{gid} /* {path} */ = {{ isa = PBXGroup; children = (); "
                f'path = {path}; sourceTree = "<group>"; }};'
            )
    for key, (tid, name) in targets.items():
        gid = folders[key][0]
        groups = f"fileSystemSynchronizedGroups = ({gid}); " if key in in_target else ""
        setting = f"SWIFT_VERSION = {swift_target}; " if swift_target else ""
        out.append(
            f"\t\t{tid} /* {name} */ = {{ isa = PBXNativeTarget; name = {name}; "
            f"{groups}buildConfigurationList = {tid}L; }};\n"
            f"\t\t{tid}L = {{ isa = XCConfigurationList; buildConfigurations = ({tid}C); }};\n"
            f"\t\t{tid}C = {{ isa = XCBuildConfiguration; name = Debug; "
            f'buildSettings = {{ {setting}PRODUCT_NAME = "$(TARGET_NAME)"; }}; }};'
        )
    out.append("\t};\n\trootObject = P1;\n}\n")
    return "\n".join(out)


def _make_part(
    root: Path,
    *,
    pbx: str | None = None,
    scheme: bool = True,
) -> None:
    proj = root / "App" / "MyApp" / "MyApp.xcodeproj"
    proj.mkdir(parents=True)
    (proj / "project.pbxproj").write_text(pbx if pbx is not None else _pbxproj())
    if scheme:
        schemes = proj / "xcshareddata" / "xcschemes"
        schemes.mkdir(parents=True)
        (schemes / "MyApp.xcscheme").write_text("<Scheme/>\n")
    for folder in ("MyApp", "MyAppTests", "MyAppUITests"):
        (root / "App" / "MyApp" / folder).mkdir(parents=True, exist_ok=True)


def _fake_xcodebuild(bin_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    exe = bin_dir / "xcodebuild"
    exe.write_text("#!/bin/sh\necho 'Xcode 26.0'\nexit 0\n")
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ.get("PATH", ""))


@pytest.fixture
def part(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A valid part with a stand-in `xcodebuild` on PATH."""
    root = tmp_path / "part"
    root.mkdir()
    _make_part(root)
    _fake_xcodebuild(tmp_path / "bin", monkeypatch)
    return root


def _run(root: Path, adopting: bool = False) -> list[CheckItem]:
    return readers.check(root, dict(_SETTINGS), adopting)


def _failing(items: list[CheckItem], *words: str) -> list[CheckItem]:
    return [i for i in items if not i.ok and any(w in i.item.lower() for w in words)]


def _assert_fails_with_fix(items: list[CheckItem], *words: str) -> None:
    bad = _failing(items, *words)
    assert bad, [(i.item, i.ok) for i in items]
    assert all(i.fix.strip() for i in bad)


# --- check ---------------------------------------------------------------------------------


def test_check_of_a_valid_part_passes_every_item(part: Path) -> None:
    items = _run(part)
    assert items
    assert all(isinstance(i, CheckItem) for i in items)
    assert all(i.ok for i in items), [i.item for i in items if not i.ok]


def test_check_of_a_valid_part_mentions_each_probe(part: Path) -> None:
    text = " ".join(i.item.lower() for i in _run(part))
    for word in ("xcode", "project", "scheme", "swift"):
        assert word in text


def test_check_fails_when_xcodebuild_is_missing(
    part: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    _assert_fails_with_fix(_run(part), "xcode")


def test_check_fails_when_the_project_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_xcodebuild(tmp_path / "bin", monkeypatch)
    root = tmp_path / "part"
    root.mkdir()
    items = _run(root)
    assert all(isinstance(i, CheckItem) for i in items)
    _assert_fails_with_fix(items, "project")


def test_check_fails_when_the_scheme_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_xcodebuild(tmp_path / "bin", monkeypatch)
    root = tmp_path / "part"
    root.mkdir()
    _make_part(root, scheme=False)
    _assert_fails_with_fix(_run(root), "scheme")


def test_check_fails_when_the_scheme_setting_names_a_scheme_that_does_not_exist(
    part: Path,
) -> None:
    settings = dict(_SETTINGS, scheme="Other")
    _assert_fails_with_fix(readers.check(part, settings, False), "scheme")


def test_check_turns_an_unparsable_project_file_into_a_failing_item(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_xcodebuild(tmp_path / "bin", monkeypatch)
    root = tmp_path / "part"
    root.mkdir()
    _make_part(root, pbx="{ objects = ( ")
    items = _run(root)
    assert all(isinstance(i, CheckItem) for i in items)
    _assert_fails_with_fix(items, "project", "pbxproj", "parse")


def test_check_requires_swift_6(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_xcodebuild(tmp_path / "bin", monkeypatch)
    root = tmp_path / "part"
    root.mkdir()
    _make_part(root, pbx=_pbxproj(swift_project="5.0"))
    _assert_fails_with_fix(_run(root, adopting=False), "swift")


def test_check_accepts_swift_5_while_adopting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_xcodebuild(tmp_path / "bin", monkeypatch)
    root = tmp_path / "part"
    root.mkdir()
    _make_part(root, pbx=_pbxproj(swift_project="5.0"))
    items = _run(root, adopting=True)
    assert all(i.ok for i in items), [i.item for i in items if not i.ok]


def test_check_accepts_swift_6_while_adopting(part: Path) -> None:
    assert all(i.ok for i in _run(part, adopting=True))


def test_check_reads_swift_version_from_the_target_before_the_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_xcodebuild(tmp_path / "bin", monkeypatch)
    ok = tmp_path / "ok"
    ok.mkdir()
    _make_part(ok, pbx=_pbxproj(swift_project="5.0", swift_target="6.0"))
    assert all(i.ok for i in _run(ok)), [i.item for i in _run(ok) if not i.ok]
    bad = tmp_path / "bad"
    bad.mkdir()
    _make_part(bad, pbx=_pbxproj(swift_project="6.0", swift_target="5.0"))
    _assert_fails_with_fix(_run(bad), "swift")


@pytest.mark.parametrize("target", ["unit", "ui"])
def test_check_fails_when_a_test_target_does_not_include_its_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    _fake_xcodebuild(tmp_path / "bin", monkeypatch)
    root = tmp_path / "part"
    root.mkdir()
    included = tuple(t for t in ("app", "unit", "ui") if t != target)
    _make_part(root, pbx=_pbxproj(in_target=included))
    _assert_fails_with_fix(_run(root), "target", "test")


@pytest.mark.parametrize("folder", ["app", "unit", "ui"])
def test_check_fails_when_a_folder_is_a_plain_group_not_a_synchronized_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, folder: str
) -> None:
    _fake_xcodebuild(tmp_path / "bin", monkeypatch)
    root = tmp_path / "part"
    root.mkdir()
    synced = tuple(t for t in ("app", "unit", "ui") if t != folder)
    _make_part(root, pbx=_pbxproj(sync=synced))
    _assert_fails_with_fix(_run(root), "synchron", "group", "folder")


def test_check_fails_on_a_nested_git_repo(part: Path) -> None:
    (part / "Vendor" / "Lib" / ".git").mkdir(parents=True)
    _assert_fails_with_fix(_run(part), "git", "nested", "repo")


def test_check_allows_the_git_folder_at_the_part_root(part: Path) -> None:
    (part / ".git").mkdir()
    assert all(i.ok for i in _run(part))


def test_every_failing_item_has_a_non_empty_fix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    root = tmp_path / "part"
    root.mkdir()
    _make_part(
        root,
        pbx=_pbxproj(swift_project="5.0", sync=(), in_target=()),
        scheme=False,
    )
    (root / "Sub" / ".git").mkdir(parents=True)
    items = _run(root)
    failing = [i for i in items if not i.ok]
    assert len(failing) >= 4
    assert all(i.fix.strip() for i in failing)


def test_check_turns_a_deeply_nested_project_file_into_a_failing_item(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_xcodebuild(tmp_path / "bin", monkeypatch)
    root = tmp_path / "part"
    root.mkdir()
    depth = 5000
    _make_part(root, pbx="{ a = " * depth + "x; " + "}; " * (depth - 1) + "}")
    items = _run(root)
    assert all(isinstance(i, CheckItem) for i in items)
    _assert_fails_with_fix(items, "project", "pbxproj", "parse")
