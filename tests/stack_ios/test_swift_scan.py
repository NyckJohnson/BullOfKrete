"""Tests for `bull.Modules.stack_ios.ios.swift_scan`.

Choices where the spec is open: the module exposes `contract_declarations(path: Path) -> list[str]`
(one string per declaration, members prefixed by their type; the exact wording is the scanner's,
tests match by regex) and `legacy_declarations(root: Path) -> list[str]` (names of `Legacy...`
types declared in any `.swift` file under `root`, in a stable order).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from bull.Modules.stack_ios.ios import readers, swift_scan


def _decls(tmp_path: Path, text: str, name: str = "C.swift") -> list[str]:
    f = tmp_path / name
    f.write_text(text)
    return swift_scan.contract_declarations(f)


def _has(lines: list[str], pattern: str) -> bool:
    return any(re.search(pattern, line) for line in lines)


# --- contract_declarations -----------------------------------------------------------------


def test_empty_file_gives_no_declarations(tmp_path: Path) -> None:
    assert _decls(tmp_path, "") == []


def test_import_only_file_gives_no_declarations(tmp_path: Path) -> None:
    assert _decls(tmp_path, "import Foundation\n") == []


def test_protocol_lists_name_and_members(tmp_path: Path) -> None:
    out = _decls(
        tmp_path,
        "public protocol CounterStore {\n"
        "    func value() -> Int\n"
        "    func increment(by: Int) -> Int\n"
        "    var count: Int { get }\n"
        "}\n",
    )
    assert _has(out, r"protocol CounterStore")
    assert _has(out, r"func value\(\) -> Int")
    assert _has(out, r"func increment\(by: Int\) -> Int")
    assert _has(out, r"var count: Int")


def test_struct_lists_name_and_stored_properties(tmp_path: Path) -> None:
    out = _decls(
        tmp_path,
        "public struct Point: Equatable {\n"
        "    public let x: Int\n"
        "    public var label: String?\n"
        "}\n",
    )
    assert _has(out, r"struct Point")
    assert _has(out, r"let x: Int")
    assert _has(out, r"var label: String\?")


def test_struct_lists_inits_and_methods(tmp_path: Path) -> None:
    out = _decls(
        tmp_path,
        "struct Box {\n    init(width: Int) {}\n    func area() -> Int { 0 }\n}\n",
    )
    assert _has(out, r"init\(width: Int\)")
    assert _has(out, r"func area\(\) -> Int")


def test_enum_lists_name_and_cases(tmp_path: Path) -> None:
    out = _decls(
        tmp_path,
        "enum Colour: String {\n"
        "    case red\n"
        '    case green = "g"\n'
        "    case custom(Int)\n"
        "}\n",
    )
    assert _has(out, r"enum Colour")
    assert _has(out, r"\bred\b")
    assert _has(out, r"\bgreen\b")
    assert _has(out, r"custom\(Int\)")


def test_class_lists_name_and_methods(tmp_path: Path) -> None:
    out = _decls(
        tmp_path,
        "public final class Engine: Runner {\n"
        "    public func start(speed: Double) throws {}\n"
        "    var running: Bool = false\n"
        "}\n",
    )
    assert _has(out, r"class Engine")
    assert _has(out, r"func start\(speed: Double\) throws")
    assert _has(out, r"var running: Bool")


def test_several_types_in_one_file_are_all_listed(tmp_path: Path) -> None:
    out = _decls(
        tmp_path,
        "protocol A { func a() }\nstruct B { var b: Int }\nenum C { case c }\nclass D {}\n",
    )
    for name in ("A", "B", "C", "D"):
        assert _has(out, rf"\b(protocol|struct|enum|class) {name}\b")


def test_private_and_fileprivate_members_are_skipped(tmp_path: Path) -> None:
    out = _decls(
        tmp_path,
        "struct Shown {\n"
        "    func visible() {}\n"
        "    var open: Int = 0\n"
        "    private func hiddenFunc() {}\n"
        "    private var hiddenVar: Int = 0\n"
        "    fileprivate func hiddenFile() {}\n"
        "    fileprivate let hiddenLet = 1\n"
        "}\n",
    )
    joined = "\n".join(out)
    assert "visible" in joined
    assert "open" in joined
    for hidden in ("hiddenFunc", "hiddenVar", "hiddenFile", "hiddenLet"):
        assert hidden not in joined


def test_private_types_are_skipped(tmp_path: Path) -> None:
    out = _decls(
        tmp_path,
        "private struct Secret { var x: Int }\nfileprivate class Quiet {}\nstruct Open {}\n",
    )
    joined = "\n".join(out)
    assert "Secret" not in joined
    assert "Quiet" not in joined
    assert "Open" in joined


def test_multi_line_signature_is_joined_into_one_line(tmp_path: Path) -> None:
    out = _decls(
        tmp_path,
        "protocol Runner {\n"
        "    func go(\n"
        "        fast: Bool,\n"
        "        times: Int\n"
        "    ) -> String\n"
        "}\n",
    )
    matching = [x for x in out if "func go" in x]
    assert len(matching) == 1
    line = matching[0]
    assert "\n" not in line
    for part in ("fast: Bool", "times: Int", "-> String"):
        assert part in line


def test_formatting_and_comments_do_not_change_the_output(tmp_path: Path) -> None:
    compact = (
        "protocol P {\n"
        "func go(a: Int, b: String) -> Bool\n"
        "var x: Int { get }\n"
        "}\n"
        "struct S { var y: Int }\n"
    )
    spread = (
        "import Foundation\n\n\n"
        "// a comment\n"
        "/// Doc comment.\n"
        "protocol P {\n"
        "    /* block\n       comment */\n"
        "    func go(\n"
        "        a: Int,\n"
        "        b: String\n"
        "    ) -> Bool // trailing\n\n"
        "    var x: Int { get }\n"
        "}\n\n"
        "struct S {\n"
        "    var y: Int // trailing\n"
        "}\n"
    )
    assert _decls(tmp_path, compact, "One.swift") == _decls(
        tmp_path, spread, "Two.swift"
    )


def test_a_changed_parameter_type_changes_the_output(tmp_path: Path) -> None:
    before = _decls(tmp_path, "protocol P { func f(a: Int) -> Int }\n", "A.swift")
    after = _decls(tmp_path, "protocol P { func f(a: String) -> Int }\n", "B.swift")
    assert before != after


def test_a_changed_return_type_changes_the_output(tmp_path: Path) -> None:
    before = _decls(tmp_path, "protocol P { func f() -> Int }\n", "A.swift")
    after = _decls(tmp_path, "protocol P { func f() -> Bool }\n", "B.swift")
    assert before != after


def test_an_added_member_changes_the_output(tmp_path: Path) -> None:
    before = _decls(tmp_path, "struct S {\n    var x: Int\n}\n", "A.swift")
    after = _decls(
        tmp_path, "struct S {\n    var x: Int\n    var y: Int\n}\n", "B.swift"
    )
    assert before != after


def test_declarations_in_comments_are_not_counted(tmp_path: Path) -> None:
    out = _decls(
        tmp_path,
        "// protocol LineGhost { func nope() }\n"
        "/* struct BlockGhost {\n    var nope: Int\n} */\n"
        "/// class DocGhost {}\n"
        "struct Real {}\n",
    )
    joined = "\n".join(out)
    assert "Real" in joined
    for ghost in ("LineGhost", "BlockGhost", "DocGhost", "nope"):
        assert ghost not in joined


def test_declarations_inside_bodies_and_strings_are_not_counted(
    tmp_path: Path,
) -> None:
    out = _decls(
        tmp_path,
        "struct Real {\n"
        "    func make() -> Int {\n"
        '        let text = "struct StringGhost"\n'
        "        struct BodyGhost { var inner: Int }\n"
        "        func helperGhost() {}\n"
        "        return text.count\n"
        "    }\n"
        "    var total: Int {\n"
        "        let localGhost = 1\n"
        "        return localGhost\n"
        "    }\n"
        "}\n",
    )
    joined = "\n".join(out)
    assert "make" in joined
    assert "total" in joined
    for ghost in ("StringGhost", "BodyGhost", "helperGhost", "localGhost", "inner"):
        assert ghost not in joined


def test_readers_contract_declarations_delegates_to_the_scanner(
    tmp_path: Path,
) -> None:
    f = tmp_path / "C.swift"
    f.write_text("protocol P { func f(a: Int) -> Int }\nstruct S { var x: Int }\n")
    assert readers.contract_declarations(f) == swift_scan.contract_declarations(f)
    assert readers.contract_declarations(f)


# --- legacy_declarations -------------------------------------------------------------------


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_legacy_declarations_finds_legacy_types_of_every_kind(tmp_path: Path) -> None:
    _write(
        tmp_path, "A.swift", "struct LegacyStruct {}\nclass LegacyClass: NSObject {}\n"
    )
    _write(tmp_path, "B.swift", "enum LegacyEnum { case a }\nprotocol LegacyProto {}\n")
    names = swift_scan.legacy_declarations(tmp_path)
    assert sorted(names) == [
        "LegacyClass",
        "LegacyEnum",
        "LegacyProto",
        "LegacyStruct",
    ]


def test_legacy_declarations_returns_names_only(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "A.swift",
        "public final class LegacyStore: Base {\n    var x = 1\n}\n",
    )
    assert swift_scan.legacy_declarations(tmp_path) == ["LegacyStore"]


def test_legacy_declarations_searches_nested_folders(tmp_path: Path) -> None:
    _write(tmp_path, "App/MyApp/MyApp/Deep/Down/Thing.swift", "struct LegacyDeep {}\n")
    assert swift_scan.legacy_declarations(tmp_path) == ["LegacyDeep"]


def test_legacy_declarations_ignores_types_without_the_prefix(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "A.swift",
        "struct Store {}\nclass NotLegacyThing {}\nstruct LegacyReal {}\n",
    )
    assert swift_scan.legacy_declarations(tmp_path) == ["LegacyReal"]


def test_legacy_declarations_ignores_mentions_in_comments_strings_and_bodies(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "A.swift",
        "// class LegacyLineGhost {}\n"
        "/* struct LegacyBlockGhost {} */\n"
        "struct Holder {\n"
        "    func use() {\n"
        '        let s = "class LegacyStringGhost"\n'
        "        let store = LegacyReal()\n"
        "        print(s, store)\n"
        "    }\n"
        "}\n"
        "extension LegacyReal {}\n"
        "struct LegacyReal {}\n",
    )
    assert swift_scan.legacy_declarations(tmp_path) == ["LegacyReal"]


def test_legacy_declarations_ignores_non_swift_files(tmp_path: Path) -> None:
    _write(tmp_path, "notes.md", "class LegacyDoc {}\n")
    _write(tmp_path, "A.swift", "struct LegacyCode {}\n")
    assert swift_scan.legacy_declarations(tmp_path) == ["LegacyCode"]


def test_legacy_declarations_of_a_root_without_swift_files_is_empty(
    tmp_path: Path,
) -> None:
    assert swift_scan.legacy_declarations(tmp_path) == []


@pytest.mark.parametrize("keyword", ["struct", "class", "enum", "protocol"])
def test_readers_legacy_declarations_delegates_to_the_scanner(
    tmp_path: Path, keyword: str
) -> None:
    _write(tmp_path, "A.swift", f"{keyword} LegacyX {{}}\n")
    assert readers.legacy_declarations(tmp_path) == ["LegacyX"]


# --- declarations wrapped after a trailing token -------------------------------------------

_MEMBERS = "    public let x: Int\n    func go() -> Int { 1 }\n"


def _same_when_wrapped(tmp_path: Path, single: str, wrapped: str) -> list[str]:
    one = _decls(tmp_path, single, "One.swift")
    many = _decls(tmp_path, wrapped, "Many.swift")
    assert one, "single-line form produced nothing"
    assert many == one
    return many


@pytest.mark.parametrize(
    ("single", "wrapped", "name"),
    [
        (
            "public struct Foo: Equatable, Sendable {\n",
            "public struct Foo: Equatable,\n    Sendable {\n",
            "Foo",
        ),
        (
            "public struct Bar: Equatable {\n",
            "public struct Bar:\n    Equatable {\n",
            "Bar",
        ),
        (
            "public struct Baz<T> where T: Hashable, T: Sendable {\n",
            "public struct Baz<T> where T: Hashable,\n    T: Sendable {\n",
            "Baz",
        ),
        (
            "public struct Qux<T> where T: Hashable {\n",
            "public struct Qux<T> where\n    T: Hashable {\n",
            "Qux",
        ),
        (
            "public struct Amp: Equatable & Sendable {\n",
            "public struct Amp: Equatable &\n    Sendable {\n",
            "Amp",
        ),
    ],
)
def test_type_header_wrapped_after_a_trailing_token_matches_single_line(
    tmp_path: Path, single: str, wrapped: str, name: str
) -> None:
    out = _same_when_wrapped(
        tmp_path, single + _MEMBERS + "}\n", wrapped + _MEMBERS + "}\n"
    )
    assert _has(out, rf"struct {name}\b")
    assert _has(out, r"let x: Int")
    assert _has(out, r"func go\(\) -> Int")


def test_members_after_a_wrapped_type_header_are_still_listed(tmp_path: Path) -> None:
    out = _decls(
        tmp_path,
        "public struct Foo: Equatable,\n    Sendable {\n    public let kept: Int\n}\n",
    )
    assert _has(out, r"struct Foo")
    assert _has(out, r"let kept: Int")


def test_protocol_member_wrapped_after_arrow_matches_single_line(
    tmp_path: Path,
) -> None:
    out = _same_when_wrapped(
        tmp_path,
        "public protocol P {\n    func f() -> Int\n    func g()\n}\n",
        "public protocol P {\n    func f() ->\n        Int\n    func g()\n}\n",
    )
    assert _has(out, r"func f\(\) -> Int")
    assert _has(out, r"func g\(\)")


def test_protocol_member_wrapped_after_comma_matches_single_line(
    tmp_path: Path,
) -> None:
    out = _same_when_wrapped(
        tmp_path,
        "public protocol P {\n    func f(a: Int, b: Int) -> Int\n}\n",
        "public protocol P {\n    func f(a: Int,\n        b: Int) -> Int\n}\n",
    )
    assert _has(out, r"func f\(a: Int, b: Int\) -> Int")


@pytest.mark.parametrize("keyword", ["throws", "async", "rethrows"])
def test_protocol_member_wrapped_after_effect_keyword_matches_single_line(
    tmp_path: Path, keyword: str
) -> None:
    out = _same_when_wrapped(
        tmp_path,
        f"public protocol P {{\n    func f() {keyword} -> Int\n}}\n",
        f"public protocol P {{\n    func f() {keyword}\n        -> Int\n}}\n",
    )
    assert _has(out, rf"func f\(\) {keyword} -> Int")


def test_protocol_member_wrapped_after_where_matches_single_line(
    tmp_path: Path,
) -> None:
    out = _same_when_wrapped(
        tmp_path,
        "public protocol P {\n    func f<T>(_ t: T) where T: Hashable, T: Sendable\n}\n",
        "public protocol P {\n    func f<T>(_ t: T) where\n        T: Hashable,\n"
        "        T: Sendable\n}\n",
    )
    assert _has(out, r"func f<T>")


def test_enum_cases_wrapped_after_comma_match_single_line(tmp_path: Path) -> None:
    out = _same_when_wrapped(
        tmp_path,
        "public enum E {\n    case a, b\n    case c\n}\n",
        "public enum E {\n    case a,\n        b\n    case c\n}\n",
    )
    for case in ("a", "b", "c"):
        assert _has(out, rf"\b{case}\b")


def test_enum_case_wrapped_after_equals_matches_single_line(tmp_path: Path) -> None:
    out = _same_when_wrapped(
        tmp_path,
        'public enum E: String {\n    case a = "x"\n    case b\n}\n',
        'public enum E: String {\n    case a =\n        "x"\n    case b\n}\n',
    )
    assert _has(out, r"\ba\b")
    assert _has(out, r"\bb\b")


def test_property_type_wrapped_after_a_dot_matches_single_line(tmp_path: Path) -> None:
    out = _same_when_wrapped(
        tmp_path,
        "public struct S {\n    public var v: Swift.Int\n    public var w: Int\n}\n",
        "public struct S {\n    public var v: Swift.\n        Int\n    public var w: Int\n}\n",
    )
    assert _has(out, r"var w: Int")


# --- operator and precedencegroup declarations do not swallow the next declaration ---------


@pytest.mark.parametrize(
    "operator",
    [
        "infix operator +=",
        "postfix operator ...",
        "infix operator &",
        "infix operator ~=",
        "prefix operator ..<",
        "infix operator ===",
    ],
)
def test_operator_declaration_does_not_swallow_the_next_type(
    tmp_path: Path, operator: str
) -> None:
    out = _decls(
        tmp_path,
        f"public struct A {{}}\n{operator}\npublic struct B {{}}\n",
    )
    assert _has(out, r"struct A\b")
    assert _has(out, r"struct B\b")


def test_precedencegroup_declaration_does_not_swallow_the_next_type(
    tmp_path: Path,
) -> None:
    out = _decls(
        tmp_path,
        "public struct A {}\n"
        "precedencegroup P { associativity: left }\n"
        "public struct B {}\n",
    )
    assert _has(out, r"struct A\b")
    assert _has(out, r"struct B\b")


def test_variadic_and_range_operators_in_signatures_keep_their_text(
    tmp_path: Path,
) -> None:
    out = _decls(
        tmp_path,
        "public struct S {\n"
        "    public func f(_ xs: Int...) -> Int { 0 }\n"
        "    public func g(r: Range<Int> = 0..<1) -> Int { 0 }\n"
        "}\n",
    )
    assert _has(out, r"Int\.\.\.")
    assert not _has(out, r"Int \.\.\.|Int\.\. \.|\.\.\. ")
    assert _has(out, r"0\.\.<1")


# --- coverage triage -----------------------------------------------------------------------


def test_legacy_declarations_skip_dot_folders_and_directories_named_like_swift_files(
    tmp_path: Path,
) -> None:
    _write(tmp_path, ".build/Hidden.swift", "struct LegacyHidden {}\n")
    (tmp_path / "Dir.swift").mkdir()
    _write(tmp_path, "Real.swift", "struct LegacyReal {}\n")
    assert swift_scan.legacy_declarations(tmp_path) == ["LegacyReal"]


def test_a_semicolon_at_depth_zero_ends_a_statement(tmp_path: Path) -> None:
    out = _decls(tmp_path, "public struct A {}; public struct B {}\n")
    assert _has(out, r"struct A")
    assert _has(out, r"struct B")


@pytest.mark.parametrize(
    "source",
    [
        "@MainActor public struct A {}\n",
        "@available(iOS 17, *) public struct A {}\n",
        "@MainActor\n@available(iOS 17, *)\npublic struct A {}\n",
    ],
)
def test_leading_attributes_do_not_hide_the_declaration(
    tmp_path: Path, source: str
) -> None:
    assert _has(_decls(tmp_path, source), r"struct A")


def test_a_statement_with_no_leading_word_is_not_a_declaration(tmp_path: Path) -> None:
    out = _decls(tmp_path, "+ 1\npublic struct A {}\n")
    assert len(out) == 1
    assert _has(out, r"struct A")


_TAIL = "    public let after: Int\n}\n"


@pytest.mark.parametrize(
    "literal",
    [
        '#"{ // " }"#',
        '"a\\n\\"b {"',
        '"a \\(f("x)")) b"',
        '"unterminated {',
        '"""\n  { // "\n  """',
        '#"raw \\#(x) { "#',
    ],
    ids=[
        "raw",
        "escapes",
        "interpolation",
        "unterminated-line",
        "multi-line",
        "raw-interp",
    ],
)
def test_string_literals_never_add_or_lose_declarations(
    tmp_path: Path, literal: str
) -> None:
    out = _decls(tmp_path, f"public struct A {{\n    public let s = {literal}\n{_TAIL}")
    assert _has(out, r"struct A")
    assert _has(out, r"let after: Int")
    assert not _has(out, r"struct B")


def test_an_unterminated_block_comment_runs_to_the_end(tmp_path: Path) -> None:
    out = _decls(tmp_path, "public struct A {}\n/* open\npublic struct B {}\n")
    assert _has(out, r"struct A")
    assert not _has(out, r"struct B")


def test_an_unterminated_multi_line_string_runs_to_the_end(tmp_path: Path) -> None:
    out = _decls(tmp_path, 'public struct A {}\nlet s = """\nabc\npublic struct B {}\n')
    assert _has(out, r"struct A")
    assert not _has(out, r"^public struct B")


def test_clean_sets_a_raw_string_aside_whole() -> None:
    cleaned, strings = swift_scan.clean('let s = #"{ // " }"#\nlet t = 1\n')
    assert strings == ['#"{ // " }"#']
    assert "//" not in cleaned
    assert "let t = 1" in cleaned


def test_clean_keeps_a_nested_interpolation_inside_its_string() -> None:
    literal = '"a \\(f("x)")) b"'
    cleaned, strings = swift_scan.clean(f"let s = {literal}\nlet t = 1\n")
    assert strings == [literal]
    assert "let t = 1" in cleaned


def test_clean_ends_an_unterminated_single_line_string_at_its_line() -> None:
    cleaned, strings = swift_scan.clean('let s = "abc\nlet t = 1\n')
    assert strings == ['"abc']
    assert "let t = 1" in cleaned


def test_clean_runs_an_unterminated_multi_line_string_to_the_end() -> None:
    cleaned, strings = swift_scan.clean('let s = """\nabc\nlet t = 1\n')
    assert len(strings) == 1
    assert "let t = 1" in strings[0]
    assert "let t = 1" not in cleaned


def test_clean_runs_an_unterminated_block_comment_to_the_end() -> None:
    cleaned, strings = swift_scan.clean("let a = 1\n/* open\nlet b = 2\n")
    assert "let a = 1" in cleaned
    assert "let b = 2" not in cleaned
    assert strings == []


@pytest.mark.parametrize(
    "tail",
    ['let s = "a\\(b', 'let s = "x \\(y(1)'],
)
def test_unclosed_interpolation_at_end_of_file_keeps_earlier_declarations(
    tmp_path: Path, tail: str
) -> None:
    text = "struct A {}\n" + tail
    decls = _decls(tmp_path, text)
    assert _has(decls, r"\bA\b")
    cleaned, literals = swift_scan.clean(text)
    assert cleaned.startswith("struct A {}")
    assert len(literals) == 1
    assert swift_scan.legacy_declarations(tmp_path) == []


def test_unclosed_interpolation_does_not_expose_following_text_as_code(
    tmp_path: Path,
) -> None:
    decls = _decls(tmp_path, 'struct A {}\nlet s = "a\\(struct LegacyB {}')
    assert _has(decls, r"\bA\b")
    assert "struct LegacyB" not in decls
    assert swift_scan.legacy_declarations(tmp_path) == []
