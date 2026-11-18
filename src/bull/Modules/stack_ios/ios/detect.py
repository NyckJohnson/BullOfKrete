"""Detects an existing Xcode project for adoption.

Reads files only (no Xcode, no subprocess): finds the app's `.xcodeproj`, parses its
`project.pbxproj`, tells the app, unit test and UI test targets apart by product type, and
proposes the stack's settings (paths POSIX and relative to `root`). What stands in the way of an
adoption comes back as issues: BLOCK (the pipeline can't adopt the app as it is), FIX (a manual
Xcode step, worded as in the setup guide's adoption steps) or NOTE.
"""

from __future__ import annotations

import os
import re
from pathlib import Path, PurePosixPath
from typing import Any

from bull.Modules.stacks.Contracts import Detection, Issue, IssueLevel

from . import pbxproj, swift_scan

_APP_TYPE = "com.apple.product-type.application"
_UNIT_TYPE = "com.apple.product-type.bundle.unit-test"
_UI_TYPE = "com.apple.product-type.bundle.ui-testing"
_NATIVE_TARGET = "PBXNativeTarget"
_SYNC_GROUP = "PBXFileSystemSynchronizedRootGroup"
_GROUP = "PBXGroup"
# Folders never searched: hidden ones, build output and third-party dependency checkouts.
_SKIP_DIRS = frozenset(
    {"DerivedData", "build", "Pods", "Carthage", "node_modules", "SourcePackages"}
)
_LOCATION_RE = re.compile(r'location\s*=\s*"([^"]*)"')
# `import UIKit` (with optional attributes such as `@preconcurrency`, an import kind such as
# `import class UIKit.UIView`, or a submodule), matched on comment- and string-free text.
_UIKIT_IMPORT_RE = re.compile(
    r"^[ \t]*(?:@\w+[ \t]+)*import[ \t]+"
    r"(?:(?:typealias|struct|class|enum|protocol|let|var|func)[ \t]+)?UIKit\b",
    re.MULTILINE,
)
_UI_TESTING_LITERAL = '"-uiTesting"'
_OBJC_SUFFIXES = (".m", ".mm")

# Any found project gets the found confidence, even when it can't be adopted as it is: the
# adoption considers only stacks above 0.5, and a BLOCK issue says what stands in the way.
_NONE_CONFIDENCE = 0.0
_FOUND_CONFIDENCE = 0.9


class _Unreadable(Exception):
    """The parsed project file doesn't have the structure an Xcode project has."""


def detect(root: Path) -> Detection:
    """How well an existing Xcode project under `root` fits the stack; never raises for content.

    No `.xcodeproj` gives a low confidence and no settings. A found project always gives a high
    confidence (a project file that can't be read, or no app target, is a BLOCK issue) and the
    settings `project`, `scheme`, `source_dir`, `test_dir`, `ui_test_dir`, `unit_test_target` and
    `ui_test_target` (each one only when it can be worked out).
    """
    projects, workspaces = _find(root)
    if not projects:
        return Detection(
            confidence=_NONE_CONFIDENCE,
            summary=f"No Xcode project (.xcodeproj) found under {root}.",
            settings={},
            issues=(),
        )
    project_dir = projects[0]
    base = project_dir.parent
    settings: dict[str, str] = {"project": _rel(root, project_dir)}
    issues: list[Issue] = []
    if len(projects) > 1:
        others = ", ".join(_rel(root, p) for p in projects[1:])
        issues.append(
            Issue(
                level=IssueLevel.NOTE,
                item=f"Several Xcode projects found; using {settings['project']} (also: {others})",
                fix="If the app is another project, set `project` to its path relative to the part folder.",
            )
        )
    issues.extend(_dependency_issues(root, base, project_dir, workspaces))

    pbx_path = project_dir / "project.pbxproj"
    try:
        project = pbxproj.parse(pbx_path.read_text(encoding="utf-8"))
        found, app_name = _analyse(root, project_dir, project, settings)
    except (
        OSError,
        UnicodeDecodeError,
        pbxproj.PbxprojError,
        _Unreadable,
        # Structure the checks below didn't foresee: still "can't be read", never a crash.
        TypeError,
        AttributeError,
        KeyError,
        ValueError,
    ) as error:
        for key in list(settings):
            if key != "project":
                del settings[key]
        issues.append(
            Issue(
                level=IssueLevel.BLOCK,
                item=f"The project file {settings['project']}/project.pbxproj can't be read ({error})",
                fix=(
                    "Open the project in Xcode and save it, or restore project.pbxproj from git; "
                    "then run the detection again."
                ),
            )
        )
        return Detection(
            confidence=_FOUND_CONFIDENCE,
            summary=f"Found Xcode project {settings['project']}, but its project file can't be read.",
            settings=settings,
            issues=tuple(issues),
        )
    issues.extend(found)
    objc = _objc_issue(root, base)
    if objc is not None:
        issues.append(objc)
    swift_count = 0
    if "source_dir" in settings:
        swift_files = _files(root / settings["source_dir"], (".swift",))
        swift_count = len(swift_files)
        issues.extend(_source_notes(root, settings["source_dir"], swift_files))
    return Detection(
        confidence=_FOUND_CONFIDENCE,
        summary=_summary(settings, app_name, swift_count),
        settings=settings,
        issues=tuple(issues),
    )


def _analyse(
    root: Path, project_dir: Path, project: dict[str, Any], settings: dict[str, str]
) -> tuple[list[Issue], str]:
    """Fills `settings` from the parsed project; returns its issues and the app target's name.

    Raises `_Unreadable` when the root object or main group is missing or isn't an object.
    """
    base = project_dir.parent
    issues: list[Issue] = []
    objects_value = project.get("objects")
    if not isinstance(objects_value, dict):
        raise _Unreadable("no objects")
    objects: dict[str, Any] = objects_value
    root_object = _root(objects, project)
    if not isinstance(_lookup(objects, root_object.get("mainGroup")), dict):
        raise _Unreadable("the main group is missing")
    targets = _native_targets(project, objects)
    app = _first_of_type(targets, _APP_TYPE)
    unit = _first_of_type(targets, _UNIT_TYPE)
    ui = _first_of_type(targets, _UI_TYPE)

    if app is None:
        issues.append(
            Issue(
                level=IssueLevel.BLOCK,
                item=f"No app target (product type application) in {settings['project']}",
                fix=(
                    "The stack adopts iOS apps only: point `project` at the app's .xcodeproj, "
                    "or add the app target in Xcode, then run the detection again."
                ),
            )
        )
    roles = (
        ("app", app, "source_dir", None),
        ("unit test", unit, "test_dir", "unit_test_target"),
        ("UI test", ui, "ui_test_dir", "ui_test_target"),
    )
    for role, target, dir_key, target_key in roles:
        if target is None:
            continue
        name = _name(target)
        if target_key is not None:
            settings[target_key] = name
        folder, issue = _folder(objects, project, target, role)
        settings[dir_key] = _join(root, base, folder)
        if issue is not None:
            issues.append(issue)

    if unit is None:
        issues.append(
            Issue(
                level=IssueLevel.FIX,
                item="No unit test target",
                fix=(
                    "In Xcode choose File > New > Target > Unit Testing Bundle (Testing System: "
                    "Swift Testing, target to be tested: the app), then set `unit_test_target` "
                    "and `test_dir`."
                ),
            )
        )
    if ui is None:
        issues.append(
            Issue(
                level=IssueLevel.FIX,
                item="No UI test target",
                fix=(
                    "In Xcode choose File > New > Target > UI Testing Bundle (target to be "
                    "tested: the app), then set `ui_test_target` and `ui_test_dir`."
                ),
            )
        )

    app_name = _name(app) if app is not None else ""
    scheme, scheme_issue = _scheme(project_dir, app_name)
    if scheme:
        settings["scheme"] = scheme
    if scheme_issue is not None:
        issues.append(scheme_issue)

    swift_issue = _swift_issue(
        project, [_name(t) for t in (app, unit, ui) if t is not None]
    )
    if swift_issue is not None:
        issues.append(swift_issue)

    isolation_issue = _isolation_issue(
        project, [_name(t) for t in (app, unit) if t is not None]
    )
    if isolation_issue is not None:
        issues.append(isolation_issue)
    return issues, app_name


def _find(root: Path) -> tuple[list[Path], list[Path]]:
    """The `.xcodeproj` and `.xcworkspace` folders under `root`, shallowest first.

    Neither is searched inside; hidden folders and `_SKIP_DIRS` are left out.
    """
    projects: list[Path] = []
    workspaces: list[Path] = []
    for dirpath, dirnames, _ in os.walk(root):
        here = Path(dirpath)
        keep: list[str] = []
        for name in sorted(dirnames):
            if name.endswith(".xcodeproj"):
                projects.append(here / name)
            elif name.endswith(".xcworkspace"):
                workspaces.append(here / name)
            elif not name.startswith(".") and name not in _SKIP_DIRS:
                keep.append(name)
        dirnames[:] = keep

    def order(path: Path) -> tuple[int, str]:
        rel = path.relative_to(root)
        return (len(rel.parts), rel.as_posix())

    return sorted(projects, key=order), sorted(workspaces, key=order)


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _join(root: Path, base: Path, folder: str) -> str:
    """`folder` (relative to the project's parent `base`) as a POSIX path relative to `root`."""
    prefix = PurePosixPath(base.relative_to(root).as_posix())
    joined = prefix / folder if str(prefix) != "." else PurePosixPath(folder)
    return joined.as_posix()


def _dependency_issues(
    root: Path, base: Path, project_dir: Path, workspaces: list[Path]
) -> list[Issue]:
    """BLOCKs for CocoaPods, Carthage, and workspaces listing projects besides the app's."""
    issues: list[Issue] = []
    folders = [root] if base == root else [root, base]
    for folder in folders:
        if (folder / "Podfile").is_file():
            issues.append(
                Issue(
                    level=IssueLevel.BLOCK,
                    item=f"CocoaPods in use ({_rel(root, folder / 'Podfile')})",
                    fix=(
                        "Move the pods to Swift Package Manager (File > Add Package Dependencies), "
                        "remove the Podfile and the Pods workspace, then run the detection again."
                    ),
                )
            )
        if (folder / "Cartfile").is_file():
            issues.append(
                Issue(
                    level=IssueLevel.BLOCK,
                    item=f"Carthage in use ({_rel(root, folder / 'Cartfile')})",
                    fix=(
                        "Move the Carthage dependencies to Swift Package Manager (File > Add "
                        "Package Dependencies), remove the Cartfile, then run the detection again."
                    ),
                )
            )
    for workspace in workspaces:
        issues.extend(_workspace_issues(root, workspace, project_dir))
    return issues


def _workspace_issues(root: Path, workspace: Path, project_dir: Path) -> list[Issue]:
    """A BLOCK when the workspace lists an `.xcodeproj` other than the app's."""
    data = workspace / "contents.xcworkspacedata"
    if not data.is_file():
        return []
    try:
        text = data.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        return [
            Issue(
                level=IssueLevel.FIX,
                item=f"The workspace {_rel(root, workspace)} can't be read ({error})",
                fix="Restore contents.xcworkspacedata from git, or delete the workspace if the app doesn't need it.",
            )
        ]
    own = os.path.normpath(project_dir)
    extra: list[str] = []
    for location in _LOCATION_RE.findall(text):
        kind, _, ref = location.partition(":")
        if not ref.endswith(".xcodeproj"):
            continue
        if kind == "absolute":
            resolved = os.path.normpath(ref)
        else:  # group:, container: and self: are relative to the workspace's folder
            resolved = os.path.normpath(workspace.parent / ref)
        if resolved != own:
            extra.append(ref)
    if not extra:
        return []
    return [
        Issue(
            level=IssueLevel.BLOCK,
            item=f"The workspace {_rel(root, workspace)} lists other projects: {', '.join(extra)}",
            fix=(
                "The stack builds one project: move those projects' code into the app's project "
                "or into Swift packages, remove them from the workspace, then run the detection again."
            ),
        )
    ]


def _native_targets(
    project: dict[str, Any], objects: dict[str, Any]
) -> list[dict[str, Any]]:
    """The project's native targets, in the root object's order (any others after)."""
    order = _root(objects, project).get("targets")
    ids = [t for t in order if isinstance(t, str)] if isinstance(order, list) else []
    ids += sorted(k for k in objects if k not in ids)
    return [
        objects[k]
        for k in ids
        if isinstance(objects.get(k), dict) and objects[k].get("isa") == _NATIVE_TARGET
    ]


def _lookup(objects: dict[str, Any], ref: object) -> Any:
    """The object a reference names, or None when `ref` is not a string id."""
    return objects.get(ref) if isinstance(ref, str) else None


def _root(objects: dict[str, Any], project: dict[str, Any]) -> dict[str, Any]:
    """The project's root object; raises `_Unreadable` when it is missing or not an object."""
    root = _lookup(objects, project.get("rootObject"))
    if not isinstance(root, dict):
        raise _Unreadable("the root object is missing")
    return root


def _first_of_type(
    targets: list[dict[str, Any]], product_type: str
) -> dict[str, Any] | None:
    return next((t for t in targets if t.get("productType") == product_type), None)


def _name(target: dict[str, Any]) -> str:
    name = target.get("name")
    return name if isinstance(name, str) else ""


def _folder(
    objects: dict[str, Any], project: dict[str, Any], target: dict[str, Any], role: str
) -> tuple[str, Issue | None]:
    """The target's folder (relative to the project's parent) and a FIX if it is a group."""
    name = _name(target)
    groups = target.get("fileSystemSynchronizedGroups")
    if isinstance(groups, list):
        for ref in groups:
            group = objects.get(ref) if isinstance(ref, str) else None
            if isinstance(group, dict) and group.get("isa") == _SYNC_GROUP:
                path = group.get("path")
                if isinstance(path, str) and path:
                    return _group_path(objects, project, ref, path), None
    group_name = name
    for child in _main_group_children(objects, project):
        path = child.get("path")
        label = child.get("name")
        if child.get("isa") == _GROUP and name in (path, label):
            group_name = path if isinstance(path, str) and path else name
            break
    return group_name, Issue(
        level=IssueLevel.FIX,
        item=f"The {role} group {group_name} is a group, not a synchronized folder",
        fix=(
            f"In Xcode's Project navigator, right-click the {group_name} group and choose "
            "Convert to Folder; if Xcode says it can't, resolve what it names and retry, then "
            "build once (Cmd-B)."
        ),
    )


def _group_path(
    objects: dict[str, Any], project: dict[str, Any], ref: str, path: str
) -> str:
    """`path` of the group `ref`, joined below its parent groups' paths up to the main group.

    A group's `path` is relative to its parent group (`sourceTree = "<group>"`). The walk stops
    at the main group, at a parent with another source tree (e.g. `SOURCE_ROOT`, whose path is
    already relative to the project's folder), or at a cycle.
    """
    parents: dict[str, str] = {}
    for key, obj in objects.items():
        children = obj.get("children") if isinstance(obj, dict) else None
        if isinstance(children, list):
            for child in children:
                if isinstance(child, str):
                    parents.setdefault(child, key)
    main = _root(objects, project).get("mainGroup")
    joined = PurePosixPath(path)
    current: str = ref
    seen = {ref}
    while True:
        node = objects.get(current)
        if not isinstance(node, dict) or node.get("sourceTree", "<group>") != "<group>":
            break
        parent = parents.get(current)
        if parent is None or parent == main or parent in seen:
            break
        seen.add(parent)
        parent_path = _lookup(objects, parent)
        parent_dir = parent_path.get("path") if isinstance(parent_path, dict) else None
        if isinstance(parent_dir, str) and parent_dir:
            joined = PurePosixPath(parent_dir) / joined
        current = parent
    return joined.as_posix()


def _main_group_children(
    objects: dict[str, Any], project: dict[str, Any]
) -> list[dict[str, Any]]:
    main = _lookup(objects, _root(objects, project).get("mainGroup"))
    children = main.get("children") if isinstance(main, dict) else None
    if not isinstance(children, list):
        return []
    found = (objects.get(c) if isinstance(c, str) else None for c in children)
    return [c for c in found if isinstance(c, dict)]


def _scheme(project_dir: Path, app_name: str) -> tuple[str, Issue | None]:
    """A shared scheme's name and an issue, if any.

    The scheme named after the app target when it is shared; otherwise the first shared scheme
    by name and a NOTE naming it; with no shared scheme, the app's name and a FIX.
    """
    folder = project_dir / "xcshareddata" / "xcschemes"
    shared = (
        sorted(p.stem for p in folder.glob("*.xcscheme")) if folder.is_dir() else []
    )
    if app_name and app_name in shared:
        return app_name, None
    if len(shared) == 1:
        return shared[0], None
    if shared:
        chosen = shared[0]
        return chosen, Issue(
            level=IssueLevel.NOTE,
            item=(
                f"Several shared schemes and none named after the app target; using scheme "
                f"{chosen} (also: {', '.join(shared[1:])})"
            ),
            fix="If the app builds with another scheme, set `scheme` to its name.",
        )
    return app_name, Issue(
        level=IssueLevel.FIX,
        item=f"No shared scheme in {project_dir.name}",
        fix=(
            "In Xcode choose Product > Scheme > Manage Schemes, tick Shared for the app's "
            "scheme (with both test targets in its Test action) and commit xcshareddata/; "
            "then set `scheme` to its name."
        ),
    )


def _swift_issue(project: dict[str, Any], targets: list[str]) -> Issue | None:
    """A NOTE for Swift 5 targets (fine while adopting), a FIX for older or unset versions."""
    versions = {t: pbxproj.build_setting(project, t, "SWIFT_VERSION") for t in targets}
    if not versions:
        return None
    shown = ", ".join(f"{t}: {v or 'not set'}" for t, v in versions.items())
    old = [t for t, v in versions.items() if v is None or not v.startswith(("5", "6"))]
    if old:
        return Issue(
            level=IssueLevel.FIX,
            item=f"Swift language version too old or not set ({shown})",
            fix=(
                f"Set Build Settings > Swift Language Version to Swift 5 or later for "
                f"{', '.join(old)}."
            ),
        )
    if any(v is not None and v.startswith("5") for v in versions.values()):
        return Issue(
            level=IssueLevel.NOTE,
            item=f"Swift 5 language mode ({shown})",
            fix=(
                "Leave the Swift Language Version as it is during the adoption; it switches to "
                "Swift 6 at the final switch."
            ),
        )
    return None


def _isolation_issue(project: dict[str, Any], targets: list[str]) -> Issue | None:
    """A FIX when Default Actor Isolation is MainActor for the app or unit test target.

    Each target's own setting wins; a target without one inherits the project's.
    """
    main_actor = [
        t
        for t in targets
        if pbxproj.build_setting(project, t, "SWIFT_DEFAULT_ACTOR_ISOLATION")
        == "MainActor"
    ]
    if not main_actor:
        return None
    return Issue(
        level=IssueLevel.FIX,
        item=f"Default Actor Isolation is MainActor ({', '.join(main_actor)})",
        fix=(
            "In Build Settings set Default Actor Isolation to nonisolated for the app and unit "
            "test targets. Legacy code may show new warnings; they aren't gated during the adoption."
        ),
    )


def _files(folder: Path, suffixes: tuple[str, ...]) -> list[Path]:
    """Files under `folder` ending in one of `suffixes`, sorted; skips what `_find` skips.

    Hidden folders, `_SKIP_DIRS` and Xcode bundles (`.xcodeproj`, `.xcworkspace`) aren't
    searched. A missing folder gives no files.
    """
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = sorted(
            d
            for d in dirnames
            if not d.startswith(".")
            and d not in _SKIP_DIRS
            and not d.endswith((".xcodeproj", ".xcworkspace"))
        )
        here = Path(dirpath)
        found.extend(here / f for f in filenames if f.endswith(suffixes))
    return sorted(found)


def _objc_issue(root: Path, base: Path) -> Issue | None:
    """A BLOCK when Objective-C sources (`.m`/`.mm`) sit under the project's folder."""
    sources = _files(base, _OBJC_SUFFIXES)
    if not sources:
        return None
    shown = ", ".join(_rel(root, p) for p in sources[:3])
    more = f" and {len(sources) - 3} more" if len(sources) > 3 else ""
    return Issue(
        level=IssueLevel.BLOCK,
        item=f"Objective-C sources in the project ({len(sources)}: {shown}{more})",
        fix=(
            "The stack adopts Swift apps only: rewrite the Objective-C code in Swift (or move it "
            "into a Swift package), remove the .m/.mm files, then run the detection again."
        ),
    )


def _source_notes(root: Path, source_dir: str, swift_files: list[Path]) -> list[Issue]:
    """NOTEs for app Swift files importing UIKit and for a missing `-uiTesting` handler.

    Comments are ignored; a `"-uiTesting"` string literal anywhere counts as handling the
    launch argument. An unreadable file counts as neither.
    """
    uikit: list[Path] = []
    handles_ui_testing = False
    for path in swift_files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        cleaned, strings = swift_scan.clean(text)
        if _UIKIT_IMPORT_RE.search(cleaned):
            uikit.append(path)
        if _UI_TESTING_LITERAL in strings:
            handles_ui_testing = True
    issues: list[Issue] = []
    if uikit:
        shown = ", ".join(_rel(root, p) for p in uikit[:3])
        more = f" and {len(uikit) - 3} more" if len(uikit) > 3 else ""
        issues.append(
            Issue(
                level=IssueLevel.NOTE,
                item=f"{len(uikit)} Swift files import UIKit ({shown}{more})",
                fix=(
                    "Nothing to do now: UIKit screens stay UIKit; the memo marks each screen "
                    "`UI: UIKit` or `UI: SwiftUI`."
                ),
            )
        )
    if not handles_ui_testing:
        issues.append(
            Issue(
                level=IssueLevel.NOTE,
                item=f"No app source in {source_dir} handles the -uiTesting launch argument",
                fix=(
                    "The baseline stage adds it: with -uiTesting the app starts from a clean, "
                    "in-memory state for the UI tests."
                ),
            )
        )
    return issues


def _summary(settings: dict[str, str], app_name: str, swift_count: int) -> str:
    parts = [f"Found Xcode project {settings['project']}"]
    if app_name:
        parts.append(f"app target {app_name}")
    else:
        parts.append("no app target")
    parts.append(f"unit tests {settings.get('unit_test_target', 'missing')}")
    parts.append(f"UI tests {settings.get('ui_test_target', 'missing')}")
    if "source_dir" in settings:
        noun = "file" if swift_count == 1 else "files"
        parts.append(f"{swift_count} Swift {noun} in {settings['source_dir']}")
    return ", ".join(parts) + "."
