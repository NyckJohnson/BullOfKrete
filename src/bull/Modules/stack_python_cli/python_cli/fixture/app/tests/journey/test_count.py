"""Journey 1, Count: `fixture_cli count` twice in an empty folder prints 1, then 2."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def _count(folder: Path) -> subprocess.CompletedProcess[str]:
    script = shutil.which("fixture_cli")
    assert script is not None, "fixture_cli is not installed: run `uv sync`"
    return subprocess.run(
        [script, "count"], cwd=folder, capture_output=True, text=True, check=False
    )


def test_count_prints_one_then_two(tmp_path: Path) -> None:
    first = _count(tmp_path)
    assert first.returncode == 0, first.stderr
    assert first.stdout.strip() == "1"
    second = _count(tmp_path)
    assert second.returncode == 0, second.stderr
    assert second.stdout.strip() == "2"
