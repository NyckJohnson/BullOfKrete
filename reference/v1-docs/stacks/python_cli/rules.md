# python_cli stack rules

Read with `ios-pipeline stack rules <agent>`: it prints the common section plus the agent's own.

## common
- Language: Python 3.11+, `from __future__ import annotations` in every file. File names end in
  `.py`, `snake_case`.
- The whole app is one installable package (`APP_PACKAGE`, under `APP_SOURCE_DIR`); modules are
  subpackages at `<APP_SOURCE_DIR>/Modules/<module>/` (literal `Modules`, capitalized — the
  pipeline's shared module convention, same for every stack, not this stack's choice). Module
  names are lowercase.
- A module's public contract lives in `Modules/<module>/Contracts/__init__.py` (literal
  `Contracts`, capitalized — same shared-driver reason as `Modules`): `typing.Protocol` classes,
  `@dataclass`es, `Enum`s. Only non-private (no leading `_`) declarations there count as contract;
  everything else is free to change without `ios-pipeline api` flagging it.
- Mocks live in `Modules/<module>/mocks/__init__.py` (lowercase — this stack's own choice, nothing
  reads it by a fixed path): `Mock<Protocol>` classes other modules' tests import.
- A file may import another module's `Contracts`/`mocks` only, and only modules its memo entry
  lists as a dependency. Nothing enforces this at the interpreter level — review catches it.
- Tests: `pytest`. Test files: `<APP_TEST_DIR>/<module>/test_<file>.py`.
- Journey (end-to-end CLI) tests: `<APP_TEST_DIR>/journey/test_<command>.py`, running the
  installed console script as a real subprocess.
- Type checking: `mypy --strict` runs as part of the build gate, not lint — a type error is a build
  failure here, the same way a Swift compiler error is for iOS.
- No bare `except:`; catch specific exceptions. No mutable default arguments.

## outline
- Protocols in the memo are Python (fence them as ```python), `typing.Protocol` subclasses.
- Data models are `@dataclass(frozen=True)` unless there's a reason for mutability (state the
  reason in the memo entry if so).
- `Files:` lines use `.py` names, e.g. `counter.py | mocks/__init__.py`.
- The CLI's commands are listed under "## Commands" (iOS's "User journeys" equivalent); each one
  names which module's `cli.py` wiring it needs.

## skeleton-builder
- Protocols and dataclasses in `Contracts/__init__.py`, exactly as the memo's Data models section.
- Stub method bodies: `raise NotImplementedError(f"{type(self).__name__}.<method>")`.
- Mocks are `Mock<Protocol>` classes in `mocks/__init__.py`, returning realistic sample data and
  recording calls made (an `.calls: list[...]` attribute, or per-method call counters).
- Placeholder test file per implementation file: `tests/<module>/test_<file>.py` with one
  `def test_placeholder() -> None: ...` (a `pass`-bodied test is fine as a placeholder — pytest
  still counts it, so the module clears the "no tests ran" gate from the start).
- A `Contracts/__init__.py` or `mocks/__init__.py` with only declarations (no method bodies beyond
  `...`/`raise NotImplementedError`) naturally has no executable lines for coverage to find, so it
  needs no marker — unlike iOS, Python's own coverage tool reports nothing to cover for a file
  with no executable statements, rather than failing it as "no data".
- Feature mode: a stub for a new requirement raises
  `NotImplementedError(f"{type(self).__name__}.<method> (feature <slug>)")`.
- If `uv` or a passing `uv sync` is missing (gates report it), don't fix the environment; list the
  exact setup.md steps under `MANUAL STEPS FOR HUMAN`.

## test-writer
- One `test_<file>.py` per implementation file, under `tests/<module>/`. Name tests by behavior:
  `def test_increment_adds_one() -> None:`, not `def test_1()`.
- `@pytest.mark.parametrize` for input tables.
- Use `tmp_path` (pytest's built-in fixture) for any test that touches the filesystem — never a
  fixed path, never the repo's own folders.
- `--fast` (`gates <module> --fast`) runs `pytest tests/<module>/` only: keep a module's tests
  runnable on their own (no cross-module fixtures that only work when every module's tests run).

## code-writer
- Depend only on the `Protocol`s and dataclasses other modules expose in their `Contracts/`;
  never reach into another module's implementation file or `mocks/`.
- Errors: raise specific, documented exception types. No bare `except:`, no swallowing an
  exception with a blanket `except Exception: pass`.
- Secrets (API keys, tokens) from environment variables or a config file outside the repo; never
  hardcoded, never logged.
- Close what you open: use `with` for files, sockets and subprocesses rather than manual
  close()/cleanup.
- Implementation details are prefixed `_` (module-private) unless another file in the module
  needs them; nothing outside `Contracts/` is part of the module's public surface.
- Docstrings on every non-private declaration in `Contracts/__init__.py`, and on tricky logic
  elsewhere.
- `cli.py` wiring is thin: parse arguments, call into the relevant module's `Contracts` interface,
  format output. Business logic belongs in the module, not in `cli.py`.

## reviewer
- Error handling: no bare `except:`; nothing swallowed silently unless the spec says so.
- Security: no secrets in source, logs, or committed files; subprocess calls build argument lists
  (never a shell string formatted with untrusted input).
- Typing: `mypy --strict` passing is necessary but not sufficient — flag an `Any` that hides a
  real type, or a `# type: ignore` without a comment saying why.
- API design: a `Contracts/__init__.py` with a leaky abstraction (a Protocol method that only
  makes sense for one concrete implementation) is a blocker.
- Style nits `ruff` would catch are not findings.
- A dataclass or Protocol with a method body beyond `...`/`raise NotImplementedError` has real
  logic and needs tests — it is not a "declarations only" file.

## ui-test-writer
- One test function per command in `tests/journey/test_<command>.py`, named after the command:
  `def test_count_command_prints_the_new_count() -> None:`.
- Run the installed console script as a real `subprocess.run([...], cwd=tmp_path, ...)` — not by
  importing and calling `cli.main()` in-process, which wouldn't catch packaging/entry-point
  mistakes. Use `tmp_path` for the working directory so journeys never touch the repo itself.
- Assert on exit code, stdout/stderr and any files the command wrote; don't assert on exact
  wording of incidental log lines.
- If a command needs an environment variable or config file to run, set it up in the test itself
  (a fixture), not by depending on the developer's machine.

## coverage-analyst
- Exemption markers are Python line comments: `# coverage-exempt: <reason>` at the end of the
  line, or `# coverage-exempt-begin: <reason>` … `# coverage-exempt-end` around a block.
- A file listed under "Files without coverage data" either has no executable code (rare once
  past the skeleton stage — Python's coverage tool usually reports nothing to cover for a pure
  declarations file, so it won't appear here at all) or never ran under test. Classify it
  `missed` unless it's genuinely declaration-only, in which case `# coverage-exempt-file: <reason>`
  in its first 20 lines.
- Typical infeasible code: `if __name__ == "__main__":` guards, OS/platform-specific branches that
  can't run in this environment, truly unreachable `assert False` defensive branches.
