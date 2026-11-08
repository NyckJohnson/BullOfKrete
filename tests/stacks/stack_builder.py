"""Helpers that build small stack folders in a temporary directory."""

from __future__ import annotations

from pathlib import Path

BASE_MANIFEST = """format = 1
[stack]
name = "NAME"
title = "Sample stack"
description = "A sample stack for tests."
language = "sample"
kind = "tool"
maturity = "experimental"
source_glob = "*.sm"
test_glob = ["test_*.sm", "*_test.sm"]
comment = "#"
scaffold = ["src", "tests"]
gitignore = [".venv/"]
agents = ["skeleton-builder", "test-writer", "code-writer", "reviewer", "coverage-analyst"]
[[stack.requires]]
tool = "uv"
hint = "https://example.invalid/uv"
[settings.source_dir]
type = "str"
default = "src/sm"
description = "Source folder."
[settings.test_dir]
type = "str"
default = "tests"
description = "Test folder."
[gates]
preflight = ["{python}", "{stack_dir}/gates.py", "preflight"]
setup = ["{python}", "{stack_dir}/gates.py", "setup"]
build_test = ["{python}", "{stack_dir}/gates.py", "build-test"]
build_test_fast = ["{python}", "{stack_dir}/gates.py", "build-test-fast", "{module}"]
lint = ["{python}", "{stack_dir}/gates.py", "lint", "{module}"]
rerun_failed = ["{python}", "{stack_dir}/gates.py", "rerun", "{failed_ids}"]
"""

JOURNEYS_LINE = 'journeys = ["{python}", "{stack_dir}/gates.py", "journeys"]\n'

RUN_SECTION = """[run]
start = ["serve", "{port}"]
ready = ["ping", "{port}"]
stop = ["halt", "{port}"]
ready_timeout = 12
"""

REQUIRED_READERS = """from __future__ import annotations


def contract_declarations(path):
    return ["decl"]


def test_results(results):
    return None


def uncovered(part_root, sources, results):
    return None


def check(part_root, settings, adopting):
    return []
"""

ALL_AGENTS = (
    '["skeleton-builder", "test-writer", "code-writer", "reviewer", '
    '"coverage-analyst", "journey-test-writer", "surveyor"]'
)


def manifest_text(
    name: str,
    *,
    replace: dict[str, str] | None = None,
    append: str = "",
) -> str:
    """The base manifest for `name`; `replace` swaps exact snippets (each must exist)."""
    text = BASE_MANIFEST.replace("NAME", name)
    for old, new in (replace or {}).items():
        assert old in text, old
        text = text.replace(old, new)
    return text + append


def write_stack(
    root: Path,
    name: str,
    *,
    manifest: str | None = None,
    readers: str | None = REQUIRED_READERS,
    extra_files: dict[str, str] | None = None,
) -> Path:
    """Create `root/<name>/` with `stack.toml`, `readers.py` and extra files."""
    folder = root / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "stack.toml").write_text(
        manifest if manifest is not None else manifest_text(name), encoding="utf-8"
    )
    if readers is not None:
        (folder / "readers.py").write_text(readers, encoding="utf-8")
    for rel, text in (extra_files or {}).items():
        (folder / rel).write_text(text, encoding="utf-8")
    return folder
