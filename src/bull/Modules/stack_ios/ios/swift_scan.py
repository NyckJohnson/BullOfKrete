"""Line scanner for Swift `Contracts/` declarations and `Legacy…` types.

Not a Swift parser: it drops comments, sets string literals aside, and walks the braces. At file
level and inside type bodies (protocol, struct, enum, class, actor, extension) each declaration
is one statement, which may span lines while brackets are open, the next line continues it
(`-> T`, `throws`, `where`, …) or the line ends unfinished (`,`, `:`, `->`, `where`, …).
Function and property bodies are skipped, except a property's accessor list (`{ get set }`),
which is part of its signature. Whitespace is normalized, so
formatting and comments never change the result; a changed type, parameter or member does.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_TYPE_KEYWORDS = frozenset(
    {"protocol", "struct", "enum", "class", "actor", "extension"}
)
_MEMBER_KEYWORDS = frozenset(
    {
        "func",
        "var",
        "let",
        "init",
        "subscript",
        "case",
        "typealias",
        "associatedtype",
        "deinit",
        "macro",
    }
)
_MODIFIERS = frozenset(
    {
        "public",
        "open",
        "internal",
        "package",
        "private",
        "fileprivate",
        "final",
        "static",
        "class",
        "override",
        "mutating",
        "nonmutating",
        "convenience",
        "required",
        "lazy",
        "weak",
        "unowned",
        "nonisolated",
        "isolated",
        "dynamic",
        "indirect",
        "optional",
        "consuming",
        "borrowing",
        "distributed",
        "prefix",
        "postfix",
        "infix",
    }
)
_HIDDEN_MODIFIERS = frozenset({"private", "fileprivate"})
_ACCESSOR_WORDS = frozenset(
    {"get", "set", "async", "throws", "mutating", "nonmutating", "_read", "_modify"}
)
# Types whose `Legacy…` names `legacy_declarations` reports (extensions only mention a type).
_LEGACY_KINDS = frozenset({"protocol", "struct", "enum", "class", "actor"})
_LEGACY_PREFIX = "Legacy"

_ATTRIBUTE_RE = re.compile(r"@[\w.]+(?:\([^()]*\))?\s*")
_WORD_RE = re.compile(r"(\w+)(\(\s*\w+\s*\))?\s*")
_NAME_RE = re.compile(r"\s*`?([^\s(<:{=,`]+)")
_ONLY_ATTRIBUTES_RE = re.compile(r"^\s*(?:@[\w.]+(?:\([^()]*\))?\s*)+$")
# A line starting with one of these continues the statement on the line before.
_CONTINUATION_RE = re.compile(r"(?:->|\{|[.:,=&?]|(?:throws|rethrows|async|where)\b)")
# A statement whose last line ends with one of these continues on the next line. Trailing
# `throws`/`async`/`rethrows` are left out: they also end complete members (`func f() throws`).
# A trailing `.`, `=` or `&` preceded by another operator character ends an operator token
# (`...`, `+=`, `&&`), not a wrapped statement, so it does not count.
_TRAILING_RE = re.compile(
    r"(?:->|[:,]|(?<![-/=+!*%<>&|^~?.])[.=&]|(?<![\w$])where)\s*$"
)
# Operator and precedence group declarations are complete on their line whatever they end with
# (`infix operator &`, `postfix operator ...`).
_OPERATOR_DECL_RE = re.compile(
    r"\s*(?:(?:prefix|postfix|infix)\s+)?(?:operator|precedencegroup)(?![\w$])"
)
_PLACEHOLDER_RE = re.compile("\x00(\\d+)\x00")


@dataclass(frozen=True)
class _Decl:
    keyword: str
    name: str
    text: str
    hidden: bool


@dataclass
class _Scope:
    """A brace level: a type body (declarations count) or any other body (skipped)."""

    is_type: bool
    path: str = ""
    hidden: bool = False
    member: _Decl | None = None
    nesting: int = 0
    content: list[str] = field(default_factory=list)


def contract_declarations(path: Path) -> list[str]:
    """One normalized line per non-private declaration in the Swift file at `path`.

    Types appear as written (`public struct Point: Equatable`); members are prefixed by their
    type's name (`Point.public let x: Int`). Raises `OSError` if the file cannot be read.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    return [d.text for d in _scan(text) if not d.hidden]


def legacy_declarations(root: Path) -> list[str]:
    """Sorted names of the `Legacy…` types declared in any `.swift` file under `root`.

    Folders whose name starts with `.` are skipped. Mentions (uses, extensions, comments,
    strings) do not count, only declarations.
    """
    names: set[str] = set()
    for path in sorted(root.rglob("*.swift")):
        relative = path.relative_to(root)
        if (
            any(part.startswith(".") for part in relative.parts[:-1])
            or not path.is_file()
        ):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for decl in _scan(text):
            if decl.keyword in _LEGACY_KINDS and decl.name.startswith(_LEGACY_PREFIX):
                names.add(decl.name)
    return sorted(names)


def _scan(text: str) -> list[_Decl]:
    """Every declaration at file level and in type bodies, private ones marked `hidden`."""
    return _Scanner(text).run()


class _Scanner:
    def __init__(self, text: str) -> None:
        self.text, self.strings = _clean(text)
        self.decls: list[_Decl] = []
        self.stack: list[_Scope] = [_Scope(is_type=True)]
        self.buf: list[str] = []
        self.depth = 0
        self.pending_end = False

    def run(self) -> list[_Decl]:
        text = self.text
        for i, char in enumerate(text):
            top = self.stack[-1]
            if not top.is_type:
                self._in_body(top, char)
                continue
            if self.pending_end and not char.isspace():
                self.pending_end = False
                statement = "".join(self.buf)
                if (
                    not _CONTINUATION_RE.match(text, i)
                    and (
                        _OPERATOR_DECL_RE.match(statement)
                        or not _TRAILING_RE.search(statement)
                    )
                    and not _ONLY_ATTRIBUTES_RE.match(statement)
                ):
                    self._flush()
            self._in_type(char)
        self._flush()
        return self.decls

    def _in_body(self, scope: _Scope, char: str) -> None:
        if char == "{":
            scope.nesting += 1
        elif char == "}":
            if scope.nesting == 0:
                self.stack.pop()
                if scope.member is not None:
                    self._emit(_with_accessors(scope.member, "".join(scope.content)))
                return
            scope.nesting -= 1
        scope.content.append(char)

    def _in_type(self, char: str) -> None:
        if char == "\n" and self.depth == 0:
            if "".join(self.buf).strip():
                self.pending_end = True
            self.buf.append(" ")
        elif char in "([" or (char == "{" and self.depth > 0):
            self.depth += 1
            self.buf.append(char)
        elif char in ")]" or (char == "}" and self.depth > 0):
            self.depth = max(0, self.depth - 1)
            self.buf.append(char)
        elif char == "{":
            self._open_body()
        elif char == "}":
            self._flush()
            if len(self.stack) > 1:
                self.stack.pop()
        elif char == ";" and self.depth == 0:
            self._flush()
        else:
            self.buf.append(char)

    def _open_body(self) -> None:
        scope = self.stack[-1]
        decl = self._take()
        if decl is not None and decl.keyword in _TYPE_KEYWORDS:
            self._emit(decl)
            if decl.keyword == "extension":
                path = decl.name
            else:
                path = f"{scope.path}.{decl.name}" if scope.path else decl.name
            self.stack.append(_Scope(is_type=True, path=path, hidden=decl.hidden))
        else:
            self.stack.append(_Scope(is_type=False, member=decl))

    def _flush(self) -> None:
        decl = self._take()
        if decl is not None:
            self._emit(decl)

    def _take(self) -> _Decl | None:
        """Classify and clear the statement collected so far."""
        statement = "".join(self.buf)
        self.buf.clear()
        self.depth = 0
        self.pending_end = False
        if not statement.strip():
            return None
        scope = self.stack[-1]
        decl = _classify(statement, self.strings, scope.hidden)
        if decl is None or not scope.path:
            return decl
        return _Decl(decl.keyword, decl.name, f"{scope.path}.{decl.text}", decl.hidden)

    def _emit(self, decl: _Decl) -> None:
        self.decls.append(decl)


def _classify(statement: str, strings: list[str], in_hidden: bool) -> _Decl | None:
    """The declaration `statement` holds, or None when it is not one."""
    text = _normalize(statement)
    pos = 0
    hidden = in_hidden
    while True:
        attribute = _ATTRIBUTE_RE.match(text, pos)
        if attribute is not None:
            pos = attribute.end()
            continue
        word = _WORD_RE.match(text, pos)
        if word is None:
            return None
        name = word.group(1)
        following = _WORD_RE.match(text, word.end())
        is_class_modifier = (
            name == "class"
            and following is not None
            and (
                following.group(1) in _MEMBER_KEYWORDS
                or following.group(1) in _MODIFIERS
            )
        )
        if (
            name in _TYPE_KEYWORDS or name in _MEMBER_KEYWORDS
        ) and not is_class_modifier:
            keyword = name
            pos = word.end()
            break
        if name not in _MODIFIERS:
            return None
        if name in _HIDDEN_MODIFIERS and word.group(2) is None:
            hidden = True
        pos = word.end()
    if keyword in ("init", "deinit", "subscript"):
        decl_name = keyword
    else:
        found = _NAME_RE.match(text, pos)
        decl_name = found.group(1) if found is not None else ""
    return _Decl(keyword, _restore(decl_name, strings), _restore(text, strings), hidden)


def _with_accessors(decl: _Decl, body: str) -> _Decl:
    """`decl` plus its accessor list when `body` is only accessor words (`get set`)."""
    if decl.keyword not in ("var", "subscript"):
        return decl
    words = body.split()
    if not words or not all(w in _ACCESSOR_WORDS for w in words):
        return decl
    return _Decl(
        decl.keyword, decl.name, f"{decl.text} {{ {' '.join(words)} }}", decl.hidden
    )


def _normalize(statement: str) -> str:
    """Collapse whitespace so layout never changes a declaration's text."""
    text = re.sub(r"\s+", " ", statement).strip()
    text = re.sub(r"([,:])(?=\S)", r"\1 ", text)
    text = re.sub(r"\s+([,:)\]])", r"\1", text)
    text = re.sub(r"([(\[])\s+", r"\1", text)
    # A member path wrapped after its dot (`Swift.` / `Int`); a dot ending an operator token
    # (`Int... x`) is left alone.
    text = re.sub(r"(?<=\w)\.\s+(?=\w)", ".", text)
    return text


def _restore(text: str, strings: list[str]) -> str:
    """Put the string literals `_clean` set aside back in place."""
    return _PLACEHOLDER_RE.sub(lambda m: strings[int(m.group(1))], text)


def _clean(text: str) -> tuple[str, list[str]]:
    """`text` without comments, each string literal replaced by a `\\x00<n>\\x00` placeholder.

    Comments keep their newlines, so line structure survives. Returns the text and the literals.
    """
    out: list[str] = []
    strings: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        char = text[i]
        if text.startswith("//", i):
            end = text.find("\n", i)
            i = n if end < 0 else end
        elif text.startswith("/*", i):
            end = _block_comment_end(text, i)
            out.append(" " + "\n" * text.count("\n", i, end))
            i = end
        elif char == '"' or (char == "#" and _raw_string_start(text, i)):
            end = _string_end(text, i)
            out.append(f"\x00{len(strings)}\x00")
            strings.append(text[i:end])
            i = end
        else:
            out.append(char)
            i += 1
    return "".join(out), strings


def clean(text: str) -> tuple[str, list[str]]:
    """`text` without comments, each string literal (interpolations included) set aside.

    Every literal becomes a `\\x00<n>\\x00` placeholder; comments keep their newlines, so line
    structure survives. Returns the cleaned text and the literals, in order.
    """
    return _clean(text)


def _block_comment_end(text: str, start: int) -> int:
    """Index just past the (possibly nested) block comment starting at `start`."""
    depth = 0
    i = start
    while i < len(text):
        if text.startswith("/*", i):
            depth += 1
            i += 2
        elif text.startswith("*/", i):
            depth -= 1
            i += 2
            if depth == 0:
                return i
        else:
            i += 1
    return len(text)


def _raw_string_start(text: str, i: int) -> bool:
    """Whether the `#` at `i` opens a raw string (`#"…"#`)."""
    j = i
    while j < len(text) and text[j] == "#":
        j += 1
    return j < len(text) and text[j] == '"'


def _string_end(text: str, start: int) -> int:
    """Index just past the string literal starting at `start` (end of text if unterminated)."""
    hashes = 0
    i = start
    while text[i] == "#":
        hashes += 1
        i += 1
    quote = '"""' if text.startswith('"""', i) else '"'
    close = quote + "#" * hashes
    escape = "\\" + "#" * hashes
    i += len(quote)
    while i < len(text):
        if text.startswith(close, i):
            return i + len(close)
        if text.startswith(escape, i):
            i += len(escape)
            if i < len(text) and text[i] == "(":
                i = _interpolation_end(text, i)
            else:
                i += 1
            continue
        if quote == '"' and text[i] == "\n":
            return i  # an unterminated single-line string ends at its line
        i += 1
    return len(text)


def _interpolation_end(text: str, start: int) -> int:
    """Index just past the `( … )` of a string interpolation starting at `start`."""
    depth = 0
    i = start
    while i < len(text):
        char = text[i]
        if char == '"' or (char == "#" and _raw_string_start(text, i)):
            i = _string_end(text, i)
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return len(text)
