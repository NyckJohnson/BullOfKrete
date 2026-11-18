"""Parses `.pbxproj` project files.

A `.pbxproj` is an old-style (OpenStep) property list: `{ key = value; ... }` dictionaries,
`( a, b, )` lists and strings, quoted or bare, with `//` and `/* */` comments. `parse` returns the
top-level dictionary with every scalar as a `str` and comments dropped; malformed input raises
`PbxprojError`. `build_setting` reads one build setting of a native target, falling back to the
project's own settings, the way Xcode resolves them (without `.xcconfig` files).
"""

from __future__ import annotations

from typing import Any

_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "0": "\0"}
# Characters that end a bare (unquoted) string.
_DELIMITERS = frozenset('{}()=;,"')


class PbxprojError(ValueError):
    """The text is not a well-formed `.pbxproj` property list."""


def parse(text: str) -> dict[str, Any]:
    """The file's top-level dictionary: dicts, lists, and `str` scalars, comments dropped.

    Raises `PbxprojError` on malformed input (unbalanced brackets, a missing `=` or `;`, an
    unterminated string or comment, an empty value, text after the top-level dictionary, or no
    dictionary at all).
    """
    parser = _Parser(text)
    parser.skip()
    if parser.peek() != "{":
        raise parser.error("expected the top-level '{'")
    value = parser.dictionary()
    parser.skip()
    if not parser.at_end():
        raise parser.error("unexpected text after the top-level dictionary")
    return value


def build_setting(
    project: dict[str, Any], target: str, key: str, configuration: str = "Debug"
) -> str | None:
    """The value of build setting `key` for the native target named `target`.

    Looks in the target's `configuration` build configuration first, then in the project's
    configuration of the same name. None when neither sets it (or the project has no such
    configuration).
    """
    objects = project.get("objects")
    if not isinstance(objects, dict):
        return None
    for obj in objects.values():
        if (
            isinstance(obj, dict)
            and obj.get("isa") == "PBXNativeTarget"
            and obj.get("name") == target
        ):
            value = _setting_in(objects, obj, key, configuration)
            if value is not None:
                return value
            break
    root = _lookup(objects, project.get("rootObject"))
    if isinstance(root, dict):
        return _setting_in(objects, root, key, configuration)
    return None


def _setting_in(
    objects: dict[str, Any], owner: dict[str, Any], key: str, configuration: str
) -> str | None:
    """`key` in the `configuration` build settings of `owner` (a target or the project)."""
    config_list = _lookup(objects, owner.get("buildConfigurationList"))
    if not isinstance(config_list, dict):
        return None
    configs = config_list.get("buildConfigurations")
    if not isinstance(configs, list):
        return None
    for ref in configs:
        config = _lookup(objects, ref)
        if isinstance(config, dict) and config.get("name") == configuration:
            settings = config.get("buildSettings")
            if isinstance(settings, dict):
                value = settings.get(key)
                return value if isinstance(value, str) else None
            return None
    return None


def _lookup(objects: dict[str, Any], ref: object) -> Any:
    """The object a reference names, or None when `ref` is not a string id."""
    return objects.get(ref) if isinstance(ref, str) else None


class _Parser:
    """A recursive-descent reader over the text, with comment skipping."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.pos = 0

    def error(self, message: str) -> PbxprojError:
        line = self.text.count("\n", 0, self.pos) + 1
        return PbxprojError(f"line {line}: {message}")

    def at_end(self) -> bool:
        return self.pos >= len(self.text)

    def peek(self) -> str:
        return self.text[self.pos] if self.pos < len(self.text) else ""

    def skip(self) -> None:
        """Skip whitespace and comments."""
        text = self.text
        while self.pos < len(text):
            char = text[self.pos]
            if char.isspace():
                self.pos += 1
            elif text.startswith("//", self.pos):
                end = text.find("\n", self.pos)
                self.pos = len(text) if end < 0 else end + 1
            elif text.startswith("/*", self.pos):
                end = text.find("*/", self.pos + 2)
                if end < 0:
                    raise self.error("unterminated comment")
                self.pos = end + 2
            else:
                return

    def expect(self, char: str) -> None:
        self.skip()
        if self.peek() != char:
            found = self.peek() or "end of file"
            raise self.error(f"expected {char!r}, found {found!r}")
        self.pos += 1

    def value(self) -> Any:
        self.skip()
        char = self.peek()
        if char == "{":
            return self.dictionary()
        if char == "(":
            return self.array()
        return self.string()

    def dictionary(self) -> dict[str, Any]:
        self.expect("{")
        result: dict[str, Any] = {}
        while True:
            self.skip()
            if self.peek() == "}":
                self.pos += 1
                return result
            if self.at_end():
                raise self.error("unterminated dictionary")
            key = self.string()
            self.expect("=")
            result[key] = self.value()
            self.expect(";")

    def array(self) -> list[Any]:
        self.expect("(")
        result: list[Any] = []
        while True:
            self.skip()
            if self.peek() == ")":
                self.pos += 1
                return result
            if self.at_end():
                raise self.error("unterminated list")
            result.append(self.value())
            self.skip()
            if self.peek() == ",":
                self.pos += 1
            elif self.peek() != ")":
                raise self.error("expected ',' or ')' in a list")

    def string(self) -> str:
        self.skip()
        if self.peek() == '"':
            return self.quoted()
        start = self.pos
        text = self.text
        while self.pos < len(text):
            char = text[self.pos]
            if (
                char.isspace()
                or char in _DELIMITERS
                or text.startswith("//", self.pos)
                or text.startswith("/*", self.pos)
            ):
                break
            self.pos += 1
        if self.pos == start:
            found = self.peek() or "end of file"
            raise self.error(f"expected a value, found {found!r}")
        return text[start : self.pos]

    def quoted(self) -> str:
        self.pos += 1  # the opening quote
        out: list[str] = []
        text = self.text
        while self.pos < len(text):
            char = text[self.pos]
            if char == '"':
                self.pos += 1
                return "".join(out)
            if char == "\\":
                if self.pos + 1 >= len(text):
                    break
                nxt = text[self.pos + 1]
                out.append(_ESCAPES.get(nxt, nxt))
                self.pos += 2
                continue
            out.append(char)
            self.pos += 1
        raise self.error("unterminated string")
