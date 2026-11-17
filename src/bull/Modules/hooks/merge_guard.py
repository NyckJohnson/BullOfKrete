"""The merge guard: `git merge` targets need a recorded full gate pass."""

from __future__ import annotations

from dataclasses import dataclass

from bull.Modules.events.Contracts import EventKind, EventLog
from bull.Modules.foundation.Contracts import AppLayout
from bull.Modules.gates.Contracts import PassRecords
from bull.Modules.gitrepo.Contracts import Git
from bull.Modules.hooks.Contracts import HookDecision
from bull.Modules.status.Contracts import Refs, StatusStore

# --- shell tokenizing (no shell is ever run; this only reads the text)

_SEPARATOR_CHARS = frozenset(";&|()")
_REDIRECT_CHARS = frozenset("<>")
_BLANKS = frozenset(" \t\r")


@dataclass(frozen=True)
class _Token:
    text: str
    is_separator: bool


def _tokenize(command: str) -> list[_Token]:
    """Splits shell text into words and command separators, quote-aware.

    Separators (`;`, `&&`, `||`, `|`, `&`, parentheses, newlines) become separator tokens.
    Redirections (`>`, `>>`, `2>&1`, `&>`, `<` ...) are dropped together with their fd
    number and target word, so they never show up as arguments.
    """
    tokens: list[_Token] = []
    word: list[str] = []
    in_word = False  # a word has started (even an empty quoted one)
    skip_next_word = False  # the next word is a redirection target
    i = 0
    n = len(command)

    def end_word() -> None:
        nonlocal in_word, skip_next_word
        if in_word:
            if skip_next_word:
                skip_next_word = False
            else:
                tokens.append(_Token("".join(word), False))
        word.clear()
        in_word = False

    while i < n:
        c = command[i]
        if c in _BLANKS:
            end_word()
            i += 1
        elif c == "\n":
            end_word()
            tokens.append(_Token(";", True))
            i += 1
        elif c == "#" and not in_word:
            while i < n and command[i] != "\n":
                i += 1
        elif c == "\\":
            if i + 1 < n and command[i + 1] == "\n":
                i += 2  # line continuation
            else:
                if i + 1 < n:
                    word.append(command[i + 1])
                in_word = True
                i += 2
        elif c == "'":
            end = command.find("'", i + 1)
            end = n if end < 0 else end
            word.append(command[i + 1 : end])
            in_word = True
            i = end + 1
        elif c == '"':
            i += 1
            while i < n and command[i] != '"':
                if command[i] == "\\" and i + 1 < n and command[i + 1] in '"\\$`':
                    i += 1
                word.append(command[i])
                i += 1
            in_word = True
            i += 1
        elif c in _REDIRECT_CHARS or (c == "&" and i + 1 < n and command[i + 1] == ">"):
            if in_word and "".join(word).isdigit():
                word.clear()  # the fd number of `2>`, not an argument
                in_word = False
            end_word()
            while i < n and command[i] in "<>&|":
                i += 1
            skip_next_word = True
        elif c in _SEPARATOR_CHARS:
            end_word()
            j = i
            while j < n and command[j] in _SEPARATOR_CHARS and j - i < 2:
                j += 1
            tokens.append(_Token(command[i:j], True))
            i = j
        else:
            word.append(c)
            in_word = True
            i += 1
    end_word()
    return tokens


def _simple_commands(command: str) -> list[list[str]]:
    """The words of each simple command in the text, in order."""
    commands: list[list[str]] = [[]]
    for token in _tokenize(command):
        if token.is_separator:
            commands.append([])
        else:
            commands[-1].append(token.text)
    return [words for words in commands if words]


# --- git argument parsing

# git's global options that take their value as the next word.
_GIT_OPTIONS_WITH_VALUE = frozenset(
    {
        "-C",
        "-c",
        "--git-dir",
        "--work-tree",
        "--namespace",
        "--super-prefix",
        "--config-env",
    }
)
# `git merge` options that take their value as the next word. Options whose value is optional
# (`--gpg-sign`/`-S`, `--log`) take it attached only (`--gpg-sign=KEY`, `-SKEY`), so the
# following word stays a ref.
_MERGE_OPTIONS_WITH_VALUE = frozenset(
    {
        "--cleanup",
        "-m",
        "-s",
        "-X",
        "-F",
        "--strategy",
        "--strategy-option",
        "--file",
        "--message",
        "--into-name",
    }
)
# These end or abandon a merge in progress; they never merge a new ref.
_MERGE_CONTROL = frozenset({"--abort", "--continue", "--quit"})


# Words that run the rest of the line as a command: `env X=1 git merge`, `sudo git merge`.
# Each maps to its options that take the next word as their value.
_WRAPPERS: dict[str, frozenset[str]] = {
    "env": frozenset({"-u", "--unset", "-C", "--chdir", "-S", "--split-string"}),
    "command": frozenset(),
    "exec": frozenset({"-a"}),
    "time": frozenset({"-f", "--format", "-o", "--output"}),
    "nohup": frozenset(),
    "sudo": frozenset(
        {
            "-u",
            "--user",
            "-g",
            "--group",
            "-h",
            "--host",
            "-p",
            "--prompt",
            "-C",
            "--close-from",
            "-D",
            "--chdir",
            "-r",
            "--role",
            "-t",
            "--type",
            "-T",
            "--command-timeout",
            "-U",
            "--other-user",
        }
    ),
}
# Shell keywords that may start a simple command before the real command word.
_KEYWORDS = frozenset({"{", "!", "then", "do", "else"})
# Shells whose `-c <string>` argument is itself a command line.
_SHELLS = frozenset({"sh", "bash", "zsh"})
# How deep `sh -c "bash -c '...'"` nesting is followed.
_MAX_SHELL_DEPTH = 4


def _is_assignment(word: str) -> bool:
    name, eq, _ = word.partition("=")
    return bool(eq) and name.isidentifier()


def _basename(word: str) -> str:
    return word.rsplit("/", 1)[-1]


def _command_start(words: list[str]) -> int:
    """Index of the real command word, past assignments, wrapper words and keywords."""
    i = 0
    while i < len(words):
        word = words[i]
        if _is_assignment(word) or word in _KEYWORDS:
            i += 1
            continue
        wrapper = _WRAPPERS.get(_basename(word))
        if wrapper is None:
            return i
        i += 1
        # The wrapper's own options (and, for `env`, its `VAR=value` arguments).
        while i < len(words):
            arg = words[i]
            if arg == "--":
                i += 1
                break
            if arg.startswith("-") and arg != "-":
                i += 2 if arg in wrapper else 1
            elif _basename(word) == "env" and _is_assignment(arg):
                i += 1
            else:
                break
    return i


def _shell_string(words: list[str]) -> str | None:
    """The command string of `sh -c <string>` (also bash, zsh), else None."""
    if not words or _basename(words[0]) not in _SHELLS:
        return None
    i = 1
    while i < len(words) and words[i].startswith("-") and words[i] != "-":
        option = words[i]
        i += 1
        if not option.startswith("--") and "c" in option[1:]:
            return words[i] if i < len(words) else None
    return None


def _merge_args(words: list[str]) -> list[str] | None:
    """The arguments after `merge` if `words` is a `git merge` command, else None."""
    if not words or _basename(words[0]) != "git":
        return None
    i = 1
    while i < len(words) and words[i].startswith("-"):
        i += 2 if words[i] in _GIT_OPTIONS_WITH_VALUE else 1
    if i >= len(words) or words[i] != "merge":
        return None
    return words[i + 1 :]


def _merge_refs(args: list[str]) -> list[str]:
    """The refs a `git merge` with these arguments would merge."""
    if any(arg in _MERGE_CONTROL for arg in args):
        return []
    refs: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--":
            refs.extend(args[i + 1 :])
            break
        if arg in _MERGE_OPTIONS_WITH_VALUE:
            i += 2
            continue
        if arg.startswith("-") and arg != "-":
            # A flag, `--opt=value`, or a short option with its value attached (`-mmsg`).
            i += 1
            continue
        refs.append(arg)
        i += 1
    return refs


def merge_targets(command: str) -> list[str]:
    """Every ref the shell command would `git merge`, in order; pure text parsing.

    Splits on `&&`, `||`, `;`, `|` and newlines (quote-aware), handles redirections and
    `git -C <dir>`, skips option values such as `-m <msg>`, and ignores `--abort`,
    `--continue` and `--quit`. Leading `VAR=value` assignments, wrapper words (`env`,
    `command`, `exec`, `time`, `nohup`, `sudo`) and the keywords `{`, `!`, `then`, `do`,
    `else` are skipped before `git`; the string of `sh -c`/`bash -c`/`zsh -c` is parsed in
    turn. Other quoted text is never read as a command. An octopus merge returns each ref.
    """
    return _targets(command, 0)


def _targets(command: str, depth: int) -> list[str]:
    targets: list[str] = []
    for words in _simple_commands(command):
        words = words[_command_start(words) :]
        inner = _shell_string(words)
        if inner is not None:
            if depth < _MAX_SHELL_DEPTH:
                targets.extend(_targets(inner, depth + 1))
            continue
        args = _merge_args(words)
        if args is not None:
            targets.extend(_merge_refs(args))
    return targets


# --- the guard


class MergeGuard:
    """Blocks a `git merge` whose target has no recorded full gate pass at its head.

    A module branch whose module has reference tests also needs its reference-test scan
    recorded. The first blocking target blocks the whole command and appends one
    `hook_block` event; an allowed command has an empty message and appends nothing.
    """

    def __init__(
        self,
        git: Git,
        passes: PassRecords,
        refs: Refs,
        status: StatusStore,
        events: EventLog,
    ) -> None:
        self._git = git
        self._passes = passes
        self._refs = refs
        self._status = status
        self._events = events

    def check(self, app: AppLayout, command: str) -> HookDecision:
        for ref in merge_targets(command):
            reason = self._block_reason(app, ref)
            if reason is not None:
                self._events.append(EventKind.HOOK_BLOCK, hook="merge", reason=reason)
                return HookDecision(False, reason)
        return HookDecision(True, "")

    def _block_reason(self, app: AppLayout, ref: str) -> str | None:
        sha = self._git.head(app.root, ref)
        if sha is None:
            return f"unknown ref {ref}: nothing to merge"
        module = self._refs.module_for_branch(ref)
        if self._passes.get(app, sha) is None:
            gates = f"bull gates {module}" if module is not None else "bull gates --all"
            return (
                f"no recorded full gate pass for {ref} at {sha}: "
                f"run `{gates}` on {ref} first"
            )
        if module is not None and self._needs_scan(module):
            return f"record the reference-test scan for {module} first"
        return None

    def _needs_scan(self, module: str) -> bool:
        for entry in self._status.load().modules:
            if entry.name == module:
                return entry.reference_tests and entry.scan is None
        return False
