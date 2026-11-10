"""Tests for `bull.Modules.coverage.triage` (sources, report, render, clean)."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from bull.Modules.coverage.Contracts import CoverageReport, Exemption
from bull.Modules.coverage.triage import LiveCoverageTriage
from bull.Modules.stacks.Contracts import CoverageData


def _write(path: Path, text: str = "x = 1\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _report(
    uncovered: Mapping[Path, tuple[int, ...]] | None = None,
    no_data: tuple[Path, ...] = (),
    invalid: tuple[str, ...] = (),
    module: str = "Counter",
) -> CoverageReport:
    return CoverageReport(
        module=module,
        uncovered=uncovered or {},
        no_data=no_data,
        exempted=(),
        invalid_markers=invalid,
    )


# ---- sources -------------------------------------------------------------


def test_sources_returns_files_matching_glob_sorted(tmp_path: Path) -> None:
    mod = tmp_path / "src" / "Counter"
    b = _write(mod / "b.py")
    a = _write(mod / "a.py")
    _write(mod / "notes.txt")
    result = LiveCoverageTriage().sources(mod, tmp_path, "*.py", [])
    assert result == [a, b]


def test_sources_includes_nested_files(tmp_path: Path) -> None:
    mod = tmp_path / "src" / "Counter"
    top = _write(mod / "a.py")
    nested = _write(mod / "sub" / "c.py")
    result = LiveCoverageTriage().sources(mod, tmp_path, "*.py", [])
    assert result == sorted([top, nested])


def test_sources_applies_exclude_globs_relative_to_part_root(tmp_path: Path) -> None:
    mod = tmp_path / "src" / "Counter"
    keep = _write(mod / "a.py")
    _write(mod / "mocks" / "__init__.py")
    result = LiveCoverageTriage().sources(mod, tmp_path, "*.py", ["*/mocks/*"])
    assert result == [keep]


def test_sources_any_exclude_glob_removes_a_file(tmp_path: Path) -> None:
    mod = tmp_path / "src" / "Counter"
    keep = _write(mod / "a.py")
    _write(mod / "gen.py")
    _write(mod / "mocks" / "m.py")
    result = LiveCoverageTriage().sources(
        mod, tmp_path, "*.py", ["src/Counter/gen.py", "*/mocks/*"]
    )
    assert result == [keep]


def test_sources_empty_module_dir_gives_empty_list(tmp_path: Path) -> None:
    mod = tmp_path / "src" / "Counter"
    mod.mkdir(parents=True)
    assert LiveCoverageTriage().sources(mod, tmp_path, "*.py", []) == []


# ---- report --------------------------------------------------------------


def test_report_lists_uncovered_lines_per_source(tmp_path: Path) -> None:
    src = _write(tmp_path / "a.py", "1\n2\n3\n4\n")
    data = CoverageData(uncovered={src: (2, 4)}, no_data=())
    rep = LiveCoverageTriage().report("Counter", [src], data, "#")
    assert rep.module == "Counter"
    assert rep.uncovered == {src: (2, 4)}
    assert rep.no_data == ()
    assert rep.invalid_markers == ()
    assert rep.clean is False


def test_report_removes_line_marker_lines_from_uncovered(tmp_path: Path) -> None:
    src = _write(tmp_path / "a.py", "1\n2  # coverage-exempt: defensive\n3\n")
    data = CoverageData(uncovered={src: (2, 3)}, no_data=())
    rep = LiveCoverageTriage().report("Counter", [src], data, "#")
    assert rep.uncovered == {src: (3,)}
    assert [ex.lines for ex in rep.exempted] == [(2,)]


def test_report_removes_block_lines_and_is_clean_when_all_exempt(
    tmp_path: Path,
) -> None:
    text = "1\n# coverage-exempt-begin: why\n3\n4\n# coverage-exempt-end\n"
    src = _write(tmp_path / "a.py", text)
    data = CoverageData(uncovered={src: (3, 4)}, no_data=())
    rep = LiveCoverageTriage().report("Counter", [src], data, "#")
    assert not rep.uncovered.get(src)
    assert rep.clean is True


def test_report_file_with_no_data_is_reported(tmp_path: Path) -> None:
    src = _write(tmp_path / "decl.py")
    data = CoverageData(uncovered={}, no_data=(src,))
    rep = LiveCoverageTriage().report("Counter", [src], data, "#")
    assert rep.no_data == (src,)
    assert rep.clean is False


def test_report_file_marker_exempts_no_data_file(tmp_path: Path) -> None:
    src = _write(tmp_path / "decl.py", "# coverage-exempt-file: declarations\nx = 1\n")
    data = CoverageData(uncovered={}, no_data=(src,))
    rep = LiveCoverageTriage().report("Counter", [src], data, "#")
    assert rep.no_data == ()
    assert any(ex.path == src and ex.lines is None for ex in rep.exempted)
    assert rep.clean is True


def test_report_file_marker_never_hides_uncovered_lines(tmp_path: Path) -> None:
    src = _write(tmp_path / "a.py", "# coverage-exempt-file: nope\nx = 1\ny = 2\n")
    data = CoverageData(uncovered={src: (2, 3)}, no_data=())
    rep = LiveCoverageTriage().report("Counter", [src], data, "#")
    assert rep.uncovered == {src: (2, 3)}
    assert rep.clean is False


def test_report_file_marker_on_file_with_data_is_unnecessary_marker(
    tmp_path: Path,
) -> None:
    src = _write(tmp_path / "a.py", "x = 1\n# coverage-exempt-file: why\ny = 2\n")
    data = CoverageData(uncovered={}, no_data=())
    rep = LiveCoverageTriage().report("Counter", [src], data, "#")
    assert rep.invalid_markers == (f"{src}:2: unnecessary file marker",)
    assert rep.clean is False


def test_report_unnecessary_file_marker_hides_no_uncovered_lines(
    tmp_path: Path,
) -> None:
    src = _write(tmp_path / "a.py", "# coverage-exempt-file: why\nx = 1\ny = 2\n")
    data = CoverageData(uncovered={src: (2, 3)}, no_data=())
    rep = LiveCoverageTriage().report("Counter", [src], data, "#")
    assert rep.uncovered == {src: (2, 3)}
    assert rep.invalid_markers == (f"{src}:1: unnecessary file marker",)


def test_report_file_marker_on_no_data_file_is_not_an_invalid_marker(
    tmp_path: Path,
) -> None:
    src = _write(tmp_path / "decl.py", "# coverage-exempt-file: declarations\nx = 1\n")
    data = CoverageData(uncovered={}, no_data=(src,))
    rep = LiveCoverageTriage().report("Counter", [src], data, "#")
    assert rep.invalid_markers == ()
    assert rep.no_data == ()


def test_report_ignores_data_for_files_outside_sources(tmp_path: Path) -> None:
    src = _write(tmp_path / "a.py")
    other = _write(tmp_path / "other.py")
    data = CoverageData(uncovered={other: (1, 2)}, no_data=(other,))
    rep = LiveCoverageTriage().report("Counter", [src], data, "#")
    assert other not in rep.uncovered
    assert other not in rep.no_data
    assert rep.clean is True


def test_report_invalid_marker_is_listed_and_exempts_nothing(tmp_path: Path) -> None:
    src = _write(tmp_path / "a.py", "1\n2  # coverage-exempt:\n3\n")
    data = CoverageData(uncovered={src: (2,)}, no_data=())
    rep = LiveCoverageTriage().report("Counter", [src], data, "#")
    assert rep.uncovered == {src: (2,)}
    assert len(rep.invalid_markers) == 1
    assert rep.invalid_markers[0].startswith(f"{src}:2:")
    assert rep.clean is False


def test_report_invalid_marker_alone_makes_report_unclean(tmp_path: Path) -> None:
    src = _write(tmp_path / "a.py", "1\n# coverage-exempt-end\n")
    data = CoverageData(uncovered={}, no_data=())
    rep = LiveCoverageTriage().report("Counter", [src], data, "#")
    assert len(rep.invalid_markers) == 1
    assert rep.clean is False


def test_report_with_full_coverage_is_clean(tmp_path: Path) -> None:
    src = _write(tmp_path / "a.py")
    data = CoverageData(uncovered={}, no_data=())
    rep = LiveCoverageTriage().report("Counter", [src], data, "#")
    assert rep.clean is True


def test_report_uses_comment_prefix(tmp_path: Path) -> None:
    src = _write(tmp_path / "a.src", "1\n2 // coverage-exempt: slash\n")
    data = CoverageData(uncovered={src: (2,)}, no_data=())
    rep = LiveCoverageTriage().report("Counter", [src], data, "//")
    assert not rep.uncovered.get(src)
    assert rep.clean is True


# ---- clean ---------------------------------------------------------------


def test_clean_true_when_nothing_to_report() -> None:
    assert _report().clean is True


def test_clean_false_with_uncovered_lines() -> None:
    assert _report(uncovered={Path("/a.py"): (1,)}).clean is False


def test_clean_false_with_no_data_files() -> None:
    assert _report(no_data=(Path("/a.py"),)).clean is False


def test_clean_false_with_invalid_markers() -> None:
    assert _report(invalid=("/a.py:1: missing reason",)).clean is False


def test_clean_ignores_exempted_entries() -> None:
    rep = CoverageReport(
        module="Counter",
        uncovered={},
        no_data=(),
        exempted=(Exemption(Path("/a.py"), (1,), "why"),),
        invalid_markers=(),
    )
    assert rep.clean is True


# ---- render --------------------------------------------------------------


def test_render_clean_report_says_coverage_clean_for_module() -> None:
    assert "coverage clean for Counter" in LiveCoverageTriage().render(_report())


def test_render_lists_uncovered_lines_with_collapsed_ranges() -> None:
    p = Path("/proj/counter.py")
    out = LiveCoverageTriage().render(_report(uncovered={p: (3, 7, 8, 9)}))
    assert f"{p}: lines 3, 7-9" in out
    assert "coverage clean" not in out


def test_render_collapses_only_consecutive_runs() -> None:
    p = Path("/proj/counter.py")
    out = LiveCoverageTriage().render(_report(uncovered={p: (1, 2, 4, 6, 7, 8, 10)}))
    assert f"{p}: lines 1-2, 4, 6-8, 10" in out


def test_render_single_line() -> None:
    p = Path("/proj/counter.py")
    out = LiveCoverageTriage().render(_report(uncovered={p: (5,)}))
    assert f"{p}: lines 5" in out


def test_render_lists_each_file_with_uncovered_lines() -> None:
    a, b = Path("/proj/a.py"), Path("/proj/b.py")
    out = LiveCoverageTriage().render(_report(uncovered={a: (1,), b: (2, 3)}))
    assert f"{a}: lines 1" in out
    assert f"{b}: lines 2-3" in out


def test_render_lists_files_without_coverage_data() -> None:
    p = Path("/proj/decl.py")
    out = LiveCoverageTriage().render(_report(no_data=(p,)))
    assert "without coverage data:" in out
    assert str(p) in out
    assert "coverage clean" not in out


def test_render_omits_no_data_heading_when_none() -> None:
    p = Path("/proj/counter.py")
    out = LiveCoverageTriage().render(_report(uncovered={p: (1,)}))
    assert "without coverage data" not in out


def test_render_lists_invalid_markers() -> None:
    msg = "/proj/a.py:4: coverage-exempt marker is missing a reason"
    out = LiveCoverageTriage().render(_report(invalid=(msg,)))
    assert msg in out
    assert "coverage clean" not in out


def test_render_lists_unnecessary_file_marker_among_invalid_markers(
    tmp_path: Path,
) -> None:
    src = _write(tmp_path / "a.py", "# coverage-exempt-file: why\nx = 1\n")
    data = CoverageData(uncovered={}, no_data=())
    triage = LiveCoverageTriage()
    out = triage.render(triage.report("Counter", [src], data, "#"))
    assert f"{src}:1: unnecessary file marker" in out
    assert "coverage clean" not in out


def test_sources_skips_directories_matching_the_glob(tmp_path: Path) -> None:
    mod = tmp_path / "src" / "Counter"
    real = _write(mod / "a.py")
    (mod / "pkg.py").mkdir()
    result = LiveCoverageTriage().sources(mod, tmp_path, "*.py", [])
    assert result == [real]


def test_sources_matches_exclude_against_full_path_outside_part_root(
    tmp_path: Path,
) -> None:
    part_root = tmp_path / "part"
    part_root.mkdir()
    mod = tmp_path / "elsewhere" / "Counter"
    keep = _write(mod / "a.py")
    gen = _write(mod / "gen.py")
    triage = LiveCoverageTriage()
    assert triage.sources(mod, part_root, "*.py", []) == sorted([keep, gen])
    result = triage.sources(mod, part_root, "*.py", [f"{gen.as_posix()}"])
    assert result == [keep]
