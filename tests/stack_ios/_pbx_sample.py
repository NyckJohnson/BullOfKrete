"""Builds small sample Xcode projects on disk for the detect and inventory tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

APP = "com.apple.product-type.application"
UNIT = "com.apple.product-type.bundle.unit-test"
UITEST = "com.apple.product-type.bundle.ui-testing"


def _render(value: object) -> str:
    if isinstance(value, dict):
        return (
            "{ " + " ".join(f'"{k}" = {_render(v)};' for k, v in value.items()) + " }"
        )
    if isinstance(value, list):
        if not value:
            return "()"
        return "( " + ", ".join(_render(v) for v in value) + ", )"
    return f'"{value}"'


def _config(swift: str | None) -> dict[str, object]:
    settings: dict[str, object] = {}
    if swift is not None:
        settings["SWIFT_VERSION"] = swift
    return {"isa": "XCBuildConfiguration", "name": "Debug", "buildSettings": settings}


def pbxproj_text(
    name: str = "MyApp",
    *,
    swift: str | None = "6.0",
    project_swift: str | None = None,
    sync: bool = True,
    unit: bool = True,
    ui: bool = True,
    spm: bool = False,
) -> str:
    """A hand-written project.pbxproj for an app named `name` with optional test targets."""
    objects: dict[str, object] = {}
    roles = [("app", name, APP, swift)]
    if unit:
        roles.append(("unit", f"{name}Tests", UNIT, swift))
    if ui:
        roles.append(("ui", f"{name}UITests", UITEST, swift))
    children: list[str] = []
    targets: list[str] = []
    for key, tname, ptype, tswift in roles:
        folder_id = f"FOLDER_{key}"
        children.append(folder_id)
        if sync:
            objects[folder_id] = {
                "isa": "PBXFileSystemSynchronizedRootGroup",
                "path": tname,
                "sourceTree": "<group>",
            }
        else:
            objects[folder_id] = {
                "isa": "PBXGroup",
                "path": tname,
                "children": [],
                "sourceTree": "<group>",
            }
        objects[f"CFG_{key}"] = _config(tswift)
        objects[f"CFGLIST_{key}"] = {
            "isa": "XCConfigurationList",
            "buildConfigurations": [f"CFG_{key}"],
        }
        target: dict[str, object] = {
            "isa": "PBXNativeTarget",
            "name": tname,
            "productName": tname,
            "productType": ptype,
            "buildConfigurationList": f"CFGLIST_{key}",
        }
        if sync:
            target["fileSystemSynchronizedGroups"] = [folder_id]
        objects[f"TARGET_{key}"] = target
        targets.append(f"TARGET_{key}")
    objects["CFG_project"] = _config(project_swift)
    objects["CFGLIST_project"] = {
        "isa": "XCConfigurationList",
        "buildConfigurations": ["CFG_project"],
    }
    objects["MAIN"] = {"isa": "PBXGroup", "children": children, "sourceTree": "<group>"}
    project: dict[str, object] = {
        "isa": "PBXProject",
        "mainGroup": "MAIN",
        "targets": targets,
        "buildConfigurationList": "CFGLIST_project",
    }
    if spm:
        objects["PKG"] = {
            "isa": "XCRemoteSwiftPackageReference",
            "repositoryURL": "https://github.com/example/pkg",
        }
        project["packageReferences"] = ["PKG"]
    objects["ROOT"] = project
    top = {
        "archiveVersion": "1",
        "objectVersion": "77",
        "objects": objects,
        "rootObject": "ROOT",
    }
    return "// !$*UTF8*$!\n" + _render(top) + "\n"


def make_project(
    root: Path,
    where: str = "App/MyApp",
    name: str = "MyApp",
    *,
    shared_scheme: bool = True,
    **options: Any,
) -> Path:
    """Write `<root>/<where>/<name>.xcodeproj` and the folders; return the .xcodeproj path."""
    base = root / where
    proj = base / f"{name}.xcodeproj"
    proj.mkdir(parents=True)
    (proj / "project.pbxproj").write_text(
        pbxproj_text(name, **options), encoding="utf-8"
    )
    for folder in (name, f"{name}Tests", f"{name}UITests"):
        (base / folder).mkdir(exist_ok=True)
    (base / name / f"{name}App.swift").write_text(
        "struct MyAppApp {}\n", encoding="utf-8"
    )
    if shared_scheme:
        schemes = proj / "xcshareddata" / "xcschemes"
        schemes.mkdir(parents=True)
        (schemes / f"{name}.xcscheme").write_text("<Scheme/>\n", encoding="utf-8")
    return proj
