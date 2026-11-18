"""Tests for `bull.Modules.stack_ios.ios.inventory` (and readers.inventory's pass-through)."""

from __future__ import annotations

from pathlib import Path

from bull.Modules.stack_ios.ios import inventory as inv
from bull.Modules.stack_ios.ios import readers

SRC = "App/Src"


def _write(root: Path, rel: str, text: str) -> None:
    path = root / SRC / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _settings() -> dict[str, object]:
    return {"source_dir": SRC}


def _section(out: str, name: str, others: list[str]) -> str:
    """The text from `name` to the next of `others` that follows it (or the end)."""
    start = out.index(name)
    ends = [
        out.index(o, start + len(name)) for o in others if o in out[start + len(name) :]
    ]
    return out[start : min(ends)] if ends else out[start:]


def test_lists_each_swift_file_and_its_top_level_types(tmp_path: Path) -> None:
    _write(
        tmp_path, "Shapes.swift", "struct Circle {}\nclass Square {}\nenum Kind {}\n"
    )
    _write(tmp_path, "Rules.swift", "protocol Drawable {}\nactor Painter {}\n")
    out = inv.inventory(tmp_path, _settings())
    assert "Shapes.swift" in out
    assert "Rules.swift" in out
    for name in ("Circle", "Square", "Kind", "Drawable", "Painter"):
        assert name in out


def test_files_in_subfolders_are_listed(tmp_path: Path) -> None:
    _write(tmp_path, "Deep/Er/Nested.swift", "struct Buried {}\n")
    out = inv.inventory(tmp_path, _settings())
    assert "Nested.swift" in out
    assert "Buried" in out


def test_non_swift_files_and_files_outside_source_dir_are_left_out(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "Notes.txt", "struct Hidden {}\n")
    other = tmp_path / "Elsewhere" / "Outside.swift"
    other.parent.mkdir(parents=True)
    other.write_text("struct Stranger {}\n", encoding="utf-8")
    _write(tmp_path, "In.swift", "struct Present {}\n")
    out = inv.inventory(tmp_path, _settings())
    assert "Present" in out
    assert "Hidden" not in out
    assert "Stranger" not in out
    assert "Outside.swift" not in out


def test_nested_types_are_not_listed_as_top_level(tmp_path: Path) -> None:
    _write(tmp_path, "Outer.swift", "struct Outer {\n    struct Inner {}\n}\n")
    out = inv.inventory(tmp_path, _settings())
    assert "Outer" in out
    assert "Inner" not in out


def test_a_file_lists_the_types_of_other_files_it_references(tmp_path: Path) -> None:
    _write(tmp_path, "User.swift", "struct Consumer {\n    let x = Provided()\n}\n")
    _write(tmp_path, "Source.swift", "struct Provided {}\n")
    out = inv.inventory(tmp_path, _settings())
    user = _section(out, "User.swift", ["Source.swift"])
    source = _section(out, "Source.swift", ["User.swift"])
    assert "Provided" in user
    assert "Consumer" not in source


def test_a_files_own_types_are_not_counted_as_references(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "Zed.swift",
        "struct Selfish {\n    static let a = Selfish()\n    func f() -> Selfish { Selfish() }\n}\n",
    )
    out = inv.inventory(tmp_path, _settings())
    assert out.count("Selfish") == 1


def test_mentions_in_comments_and_strings_are_not_references(tmp_path: Path) -> None:
    _write(tmp_path, "Target.swift", "struct Gamma {}\n")
    _write(
        tmp_path,
        "Talker.swift",
        "// Gamma in a line comment\n/* Gamma in a block */\nstruct Talker {\n"
        '    let s = "Gamma in a string"\n}\n',
    )
    out = inv.inventory(tmp_path, _settings())
    talker = _section(out, "Talker.swift", ["Target.swift"])
    assert "Gamma" not in talker


def test_references_match_whole_names_only(tmp_path: Path) -> None:
    _write(tmp_path, "Small.swift", "struct Beta {}\n")
    _write(tmp_path, "Big.swift", "struct BetaHelper {\n    let x = 1\n}\n")
    out = inv.inventory(tmp_path, _settings())
    big = _section(out, "Big.swift", ["Small.swift"])
    assert big.count("Beta") == 1  # only its own BetaHelper, no reference to Beta


def test_files_appear_in_sorted_order_whatever_the_creation_order(
    tmp_path: Path,
) -> None:
    for name in ("Cc", "Aa", "Bb"):
        _write(tmp_path, f"{name}.swift", f"struct Type{name} {{}}\n")
    out = inv.inventory(tmp_path, _settings())
    assert out.index("Aa.swift") < out.index("Bb.swift") < out.index("Cc.swift")


def test_output_is_deterministic(tmp_path: Path) -> None:
    _write(tmp_path, "One.swift", "struct First { let t = Second() }\n")
    _write(tmp_path, "Two.swift", "struct Second { let t = First() }\n")
    assert inv.inventory(tmp_path, _settings()) == inv.inventory(tmp_path, _settings())


def test_readers_inventory_returns_what_inventory_returns(tmp_path: Path) -> None:
    _write(tmp_path, "One.swift", "struct First {}\n")
    assert readers.inventory(tmp_path, _settings()) == inv.inventory(
        tmp_path, _settings()
    )
