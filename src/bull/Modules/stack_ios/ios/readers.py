"""The stack's readers: the functions bull imports from this folder.

Contracts and `Legacy…` types are read by `swift_scan`; test results and coverage come from the
result bundles (`xcresults`); `detect` and `inventory` serve adoptions. `check` probes the part's
setup without running Xcode: only `xcodebuild` on PATH, the files on disk and the parsed
`.pbxproj`.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from bull.Modules.stacks.Contracts import CheckItem, CoverageData, Detection, TestRun

from . import detect as _detect
from . import inventory as _inventory
from . import pbxproj, swift_scan, xcresults

_SYNC_GROUP = "PBXFileSystemSynchronizedRootGroup"
_NATIVE_TARGET = "PBXNativeTarget"
# Folders never searched for nested repositories (bull's own state, Xcode's build output).
_SKIP_DIRS = frozenset({".git", ".bull", "DerivedData"})


def contract_declarations(path: Path) -> list[str]:
    """One line per non-private declaration in the Swift file at `path` (see `swift_scan`)."""
    return swift_scan.contract_declarations(path)


def test_results(results: Path) -> TestRun | None:
    """Test count and failed ids from the result bundles in `results`."""
    return xcresults.test_results(results)


def uncovered(part_root: Path, sources: Sequence[Path], results: Path) -> CoverageData:
    """Uncovered lines of `sources` from the result bundles in `results`."""
    return xcresults.uncovered(part_root, sources, results)


def check(
    part_root: Path, settings: Mapping[str, object], adopting: bool
) -> list[CheckItem]:
    """One item per probe of the part's setup; never raises.

    Xcode present (`xcodebuild` on PATH), project and shared scheme exist, the project file
    parses, Swift 6 in the app and test targets (Swift 5 too while `adopting`), each target's
    folder is a synchronized folder the target includes, and no git repository below the part
    root.
    """
    items = [_xcode_item()]
    project_rel = _str(settings, "project")
    scheme = _str(settings, "scheme")
    project_dir = part_root / project_rel
    pbx_path = project_dir / "project.pbxproj"

    if not project_rel or not pbx_path.is_file():
        items.append(
            CheckItem(
                ok=False,
                item=f"Xcode project {project_rel or '(not set)'} exists",
                fix=(
                    "Create the app's project in Xcode at that path (see `bull stack setup`), "
                    "or set `project` to the .xcodeproj's path relative to the part folder."
                ),
            )
        )
    else:
        items.append(
            CheckItem(ok=True, item=f"Xcode project {project_rel} exists", fix="")
        )

    scheme_file = project_dir / "xcshareddata" / "xcschemes" / f"{scheme}.xcscheme"
    items.append(
        CheckItem(
            ok=bool(scheme) and scheme_file.is_file(),
            item=f"Shared scheme {scheme or '(not set)'} exists",
            fix=(
                "In Xcode choose Product > Scheme > Manage Schemes, tick Shared for the app's "
                "scheme and commit xcshareddata/; or set `scheme` to the shared scheme's name."
            ),
        )
    )

    if pbx_path.is_file():
        items.extend(_project_items(pbx_path, settings, adopting))
    items.append(_nested_repo_item(part_root))
    return items


def detect(root: Path) -> Detection:
    """How well an existing Xcode project under `root` fits the stack."""
    return _detect.detect(root)


def inventory(root: Path, settings: Mapping[str, object]) -> str:
    """Markdown inventory of the project's types and references."""
    return _inventory.inventory(root, settings)


def legacy_declarations(path: Path) -> list[str]:
    """Sorted names of the `Legacy…` types declared in `.swift` files under `path`."""
    return swift_scan.legacy_declarations(path)


def _str(settings: Mapping[str, object], key: str) -> str:
    value = settings.get(key)
    return value if isinstance(value, str) else ""


def _xcode_item() -> CheckItem:
    found = shutil.which("xcodebuild") is not None
    return CheckItem(
        ok=found,
        item="Xcode is installed (xcodebuild on PATH)",
        fix=(
            "Install Xcode 26 or later from the App Store, open it once, then run "
            "`xcode-select -s /Applications/Xcode.app`."
        ),
    )


def _project_items(
    pbx_path: Path, settings: Mapping[str, object], adopting: bool
) -> list[CheckItem]:
    """Items read from the parsed project file: Swift version, folders and targets."""
    try:
        project = pbxproj.parse(pbx_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, pbxproj.PbxprojError) as error:
        return [
            CheckItem(
                ok=False,
                item=f"Xcode project file {pbx_path.name} parses ({error})",
                fix=(
                    "Open the project in Xcode and save it, or restore project.pbxproj from "
                    "git; then run the check again."
                ),
            )
        ]
    objects = project.get("objects")
    objects = objects if isinstance(objects, dict) else {}
    scheme = _str(settings, "scheme")
    roles = [
        ("app", scheme, _str(settings, "source_dir")),
        ("unit test", _str(settings, "unit_test_target"), _str(settings, "test_dir")),
        ("UI test", _str(settings, "ui_test_target"), _str(settings, "ui_test_dir")),
    ]
    items = [_swift_item(project, [t for _, t, _ in roles], adopting)]
    for role, target, folder in roles:
        items.extend(_folder_items(objects, role, target, folder))
    return items


def _swift_item(
    project: dict[str, Any], targets: list[str], adopting: bool
) -> CheckItem:
    versions = {t: pbxproj.build_setting(project, t, "SWIFT_VERSION") for t in targets}
    allowed = ("5", "6") if adopting else ("6",)
    bad = [t for t, v in versions.items() if v is None or not v.startswith(allowed)]
    shown = ", ".join(f"{t}: {v or 'not set'}" for t, v in versions.items())
    mode = "Swift 6 (Swift 5 allowed while adopting)" if adopting else "Swift 6"
    return CheckItem(
        ok=not bad,
        item=f"Swift language mode is {mode} ({shown})",
        fix=(
            f"Set Build Settings > Swift Language Version to Swift 6 for {', '.join(bad)} "
            "(SWIFT_VERSION = 6.0)."
            if bad
            else ""
        ),
    )


def _folder_items(
    objects: dict[str, Any], role: str, target: str, folder: str
) -> list[CheckItem]:
    """Whether `folder` is a synchronized folder and the `role` target includes it."""
    name = Path(folder).name
    synced = {
        key
        for key, obj in objects.items()
        if isinstance(obj, dict)
        and obj.get("isa") == _SYNC_GROUP
        and obj.get("path") == name
    }
    sync_item = CheckItem(
        ok=bool(name) and bool(synced),
        item=f"The {role} folder {folder or '(not set)'} is a synchronized folder, not a group",
        fix=(
            f"In Xcode, right-click the {name or role} group in the navigator and choose "
            "Convert to Folder (or set the folder setting to the target's real folder)."
        ),
    )
    owner = next(
        (
            obj
            for obj in objects.values()
            if isinstance(obj, dict)
            and obj.get("isa") == _NATIVE_TARGET
            and obj.get("name") == target
        ),
        None,
    )
    groups = owner.get("fileSystemSynchronizedGroups") if owner is not None else None
    included = isinstance(groups, list) and any(g in synced for g in groups)
    if owner is None:
        fix = (
            f"Add a target named {target or '(not set)'} in Xcode, or set the {role} target "
            "setting to its name."
        )
    else:
        fix = (
            f"In Xcode, select the {name or role} folder and tick {target} under Target "
            "Membership in the File inspector."
        )
    target_item = CheckItem(
        ok=included,
        item=f"The {role} target {target or '(not set)'} includes its folder {folder}",
        fix=fix,
    )
    return [sync_item, target_item]


def _nested_repo_item(part_root: Path) -> CheckItem:
    """Fails when a `.git` folder or file sits anywhere below the part root."""
    nested: list[str] = []
    for dirpath, dirnames, filenames in os.walk(part_root):
        here = Path(dirpath)
        if here != part_root and (".git" in dirnames or ".git" in filenames):
            nested.append(here.relative_to(part_root).as_posix())
        dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS)
    if not nested:
        return CheckItem(ok=True, item="No nested git repositories in the part", fix="")
    return CheckItem(
        ok=False,
        item=f"Nested git repositories in the part: {', '.join(nested)}",
        fix=(
            "Remove the nested .git (or turn it into a Swift package dependency) so the "
            "app's one repository holds all its code."
        ),
    )
