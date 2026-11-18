"""Test counts, failed ids and coverage from result bundles.

Bundles are the `*.xcresult` folders `gates.py` writes into the results folder
(`<step>.xcresult`). Test results come from the newest bundle, the one the step just run wrote;
coverage from `build-test.xcresult` (the full run) when it exists, else the newest bundle.

Tests: `xcrun xcresulttool get test-results tests --path <bundle>` gives a tree of
`{nodeType, nodeIdentifier, result, children}`. Every `Test Case` node is a test; a failed one
adds its `nodeIdentifier` (`Suite/test()`) to `failed`, in tree order. A test bundle that failed
to launch has no `Test Case` below it, so it adds nothing.

Coverage: `xcrun xccov view --report --json <bundle>` lists the source paths recorded at build
time (absolute, on the machine that built). A source matches the recorded path that ends in its
part-root-relative path; its lines come from `xccov view --archive --file <recorded path>`.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterator, Sequence
from pathlib import Path

from bull.Modules.stacks.Contracts import CoverageData, TestRun

_BUNDLE_GLOB = "*.xcresult"
_COVERAGE_BUNDLE = "build-test.xcresult"
_TEST_CASE = "Test Case"
_FAILED = "Failed"


def test_results(results: Path) -> TestRun | None:
    """Test count and failed ids from the newest result bundle in `results`.

    None when there is no bundle, or when `xcresulttool` can't read it (a run that stopped
    before writing results).
    """
    bundle = _newest(results)
    if bundle is None:
        return None
    data = _json(
        ["xcrun", "xcresulttool", "get", "test-results", "tests", "--path", str(bundle)]
    )
    if not isinstance(data, dict):
        return None
    count = 0
    failed: list[str] = []
    for node in _cases(data.get("testNodes")):
        count += 1
        if node.get("result") == _FAILED:
            failed.append(str(node.get("nodeIdentifier") or node.get("name") or ""))
    return TestRun(count=count, failed=tuple(failed))


def uncovered(part_root: Path, sources: Sequence[Path], results: Path) -> CoverageData:
    """Uncovered lines of `sources` from the result bundles in `results`.

    A source with executable lines never run maps to them, ascending; a fully covered source is
    left out; a source the bundle has no data for (or with no bundle at all) is in `no_data`.
    """
    if not sources:
        return CoverageData(uncovered={}, no_data=())
    bundle = _coverage_bundle(results)
    report = (
        _json(["xcrun", "xccov", "view", "--report", "--json", str(bundle)])
        if bundle is not None
        else None
    )
    recorded = _recorded_paths(report)
    found: dict[Path, tuple[int, ...]] = {}
    no_data: list[Path] = []
    for source in sources:
        path = _match(part_root, source, recorded)
        lines = (
            None if path is None or bundle is None else _uncovered_lines(bundle, path)
        )
        if lines is None:
            no_data.append(source)
        elif lines:
            found[source] = lines
    return CoverageData(uncovered=found, no_data=tuple(no_data))


# --- helpers -------------------------------------------------------------------------------


def _bundles(results: Path) -> list[Path]:
    if not results.is_dir():
        return []
    return [p for p in results.glob(_BUNDLE_GLOB) if p.is_dir()]


def _newest(results: Path) -> Path | None:
    bundles = _bundles(results)
    if not bundles:
        return None
    return max(bundles, key=lambda p: (p.stat().st_mtime, p.name))


def _coverage_bundle(results: Path) -> Path | None:
    full = results / _COVERAGE_BUNDLE
    return full if full.is_dir() else _newest(results)


def _json(argv: list[str]) -> object:
    """The parsed JSON a tool prints; None when it can't run, fails or prints no JSON."""
    try:
        done = subprocess.run(argv, capture_output=True, text=True, check=False)
    except OSError:
        return None
    if done.returncode != 0 or not done.stdout:
        return None
    try:
        parsed: object = json.loads(done.stdout)
    except json.JSONDecodeError:
        return None
    return parsed


def _cases(nodes: object) -> Iterator[dict[str, object]]:
    """Every `Test Case` node below `nodes`, in tree order."""
    if not isinstance(nodes, list):
        return
    for node in nodes:
        if not isinstance(node, dict):
            continue
        if node.get("nodeType") == _TEST_CASE:
            yield node
        else:
            yield from _cases(node.get("children"))


def _recorded_paths(report: object) -> list[str]:
    if not isinstance(report, dict):
        return []
    targets = report.get("targets")
    paths: list[str] = []
    for target in targets if isinstance(targets, list) else []:
        files = target.get("files") if isinstance(target, dict) else None
        for entry in files if isinstance(files, list) else []:
            path = entry.get("path") if isinstance(entry, dict) else None
            if isinstance(path, str) and path:
                paths.append(path)
    return paths


def _match(part_root: Path, source: Path, recorded: list[str]) -> str | None:
    """The recorded path ending in `source`'s part-root-relative path, if any."""
    try:
        rel = source.relative_to(part_root).as_posix()
    except ValueError:
        rel = source.as_posix()
    for path in recorded:
        if path == rel or path.endswith("/" + rel.lstrip("/")):
            return path
    return None


def _uncovered_lines(bundle: Path, path: str) -> tuple[int, ...] | None:
    """Executable lines of `path` run zero times; None when xccov has no lines for it."""
    data = _json(
        ["xcrun", "xccov", "view", "--archive", "--file", path, "--json", str(bundle)]
    )
    if not isinstance(data, dict):
        return None
    lines = data.get(path)
    if lines is None and len(data) == 1:
        lines = next(iter(data.values()))
    if not isinstance(lines, list):
        return None
    missed = {
        line["line"]
        for line in lines
        if isinstance(line, dict)
        and line.get("isExecutable") is True
        and line.get("executionCount") == 0
        and isinstance(line.get("line"), int)
    }
    return tuple(sorted(missed))
