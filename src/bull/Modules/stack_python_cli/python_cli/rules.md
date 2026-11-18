# Python CLI stack: rules

`bull stack rules <agent>` prints `## common` plus that agent's section; `bull stack rules outline`
prints `## outline` only.

## common
- You write Python 3.11+. Put `from __future__ import annotations` at the top of every source
  file. File names are `snake_case.py`.
- The app is one installable package, `<source_dir>` (default `src/<package>`). Modules are
  subpackages at `<source_dir>/Modules/<module>/`. `Modules` is capitalized because that is bull's
  module convention, the same for every stack. Module names are lowercase.
- A module's contract is `Modules/<module>/Contracts/__init__.py` (`Contracts` is capitalized for
  the same reason). It holds `typing.Protocol` classes, `@dataclass`es, `Enum`s, public functions
  and type aliases. Only public names (no leading `_`) count. `bull api` lists them with Python's
  `ast`, so reformatting doesn't change the contract, while a changed signature, a changed field
  type or an added or removed public member does.
- Mocks live in `Modules/<module>/mocks/__init__.py` (lowercase): `Mock<Protocol>` classes that
  other modules' tests import. Mocks are left out of coverage (the `coverage.exclude` setting
  defaults to `*/mocks/*`).
- A file imports another module's `Contracts` or `mocks` only, and only from modules its memo
  entry lists under `Depends on`. Python doesn't enforce this; review does.
- Tests use pytest and live in `<test_dir>/<module>/test_<file>.py`. Journey tests live in
  `<test_dir>/journey/test_<command>.py` (by default `tests/journey/`).
- `mypy --strict` runs in the build gate: a type error fails the build, not lint.
- Lint is `ruff check` plus `ruff format --check`. It uses the app's own ruff config if it has
  one, else the stack's `lint/ruff.toml`. The `N` (naming) rules are off so the capitalized
  `Modules` and `Contracts` folders pass.
- No bare `except:`; catch specific exceptions. No mutable default arguments.
- Interfaces (json-schema): a module that provides or consumes an interface declares, in its
  `Contracts/__init__.py`, a `@dataclass` named after the schema's `title`, with one field per
  schema property and the matching type: `string` → `str`, `integer` → `int`, `number` →
  `float`, `boolean` → `bool`, `array` → `list[...]`. A property not in `required` is
  `X | None`. `bull gates` checks both sides against the schema file. A mock standing in for a
  consumed interface returns instances of that dataclass, with sample values for every field.

## outline
- Protocols in the memo are Python, fenced ```` ```python ````, as `typing.Protocol` subclasses.
- Data models are `@dataclass(frozen=True)` unless the memo entry says why one must be mutable.
- `Files:` lines use `.py` paths relative to the module folder, e.g.
  `Contracts/__init__.py, mocks/__init__.py | counter.py`.
- The CLI's commands go under `## Commands`, each naming the module that implements it. Each user
  journey under `## User journeys` names the commands it runs; journey tests run them.
- The console script is wired in `<source_dir>/cli.py` (`main()`), outside `Modules/`. List it as
  app shell, not as a module file. It stays thin: parse arguments, call a module's contract,
  print.
- An interface a module provides or consumes is a dataclass in its `Contracts` (see `## common`).

## skeleton-builder
- `Contracts/__init__.py` holds the Protocols, dataclasses and enums exactly as the memo gives
  them.
- Stub method bodies are `raise NotImplementedError(f"{type(self).__name__}.<method>")`. In
  feature mode, use `NotImplementedError(f"{type(self).__name__}.<method> (feature <slug>)")`.
- Mocks are `Mock<Protocol>` classes in `mocks/__init__.py`. They return realistic sample data and
  record calls (a `calls: list[...]` attribute or per-method counters).
- Write one placeholder test per implementation file, `tests/<module>/test_<file>.py`, holding
  `def test_placeholder() -> None: ...`, so every module runs at least one test from the start.
- A Contracts or mocks file with only declarations (bodies `...` or `raise NotImplementedError`)
  has nothing for coverage to find and needs no marker.
- If `uv` is missing or `uv sync` fails (the preflight gate says so), don't repair the
  environment. List the `bull stack setup` steps under `MANUAL STEPS FOR HUMAN`.

## test-writer
- Write one `test_<file>.py` per implementation file, in `tests/<module>/`. Name tests by behavior
  (`test_increment_adds_one`, not `test_1`).
- Use `@pytest.mark.parametrize` for input tables.
- Use `tmp_path` for anything touching the filesystem; never a fixed path or the repo's own
  folders.
- `bull gates <module> --fast` runs `pytest tests/<module>` alone. Keep each module's tests
  runnable on their own: no fixtures that only exist when every module's tests run.
- Run `uv run ruff format` and `uv run ruff check --fix` on every test file you write before you
  return.

## code-writer
- Depend only on the Protocols and dataclasses other modules expose in `Contracts/`. Never import
  another module's implementation files or its `mocks/`.
- Raise specific, documented exception types. No bare `except:`, no `except Exception: pass`.
- Secrets come from environment variables or a config file outside the repo. Never hardcode or
  log them.
- Use `with` for files, sockets and subprocesses.
- Prefix implementation details with `_` unless another file in the module needs them. Nothing
  outside `Contracts/` is public.
- Write docstrings on every public declaration in `Contracts/__init__.py`, and on tricky logic.
- `cli.py` stays thin (see `## outline`); logic belongs in modules.
- Iterate with `bull gates --failed` (it reruns the tests that just failed), then confirm with
  `bull gates <module> --fast`.

## reviewer
- Error handling: no bare `except:`; nothing swallowed unless the spec says so.
- Security: no secrets in source, logs or committed files. Subprocess calls use argument lists,
  never a shell string built from untrusted input.
- Typing: passing `mypy --strict` is not enough. Flag an `Any` hiding a real type, and a
  `# type: ignore` without a comment saying why.
- API design: a Protocol method that only makes sense for one implementation is a blocker.
- Style nits ruff would catch are not findings.
- A dataclass or Protocol whose methods have real bodies (beyond `...` or
  `raise NotImplementedError`) has logic that needs tests; it is not declaration-only.
- Imports across modules go through the `Contracts` or `mocks` of declared dependencies only (see
  `## common`).

## coverage-analyst
- Markers are Python comments: `# coverage-exempt: <reason>` at the end of a line, or
  `# coverage-exempt-begin: <reason>` … `# coverage-exempt-end` around a block.
- A file under "Files without coverage data" never ran under test, or has no executable code.
  Classify it `missed` unless it is declaration-only; then add `# coverage-exempt-file: <reason>`
  in its first 10 lines.
- Code that runs only in a subprocess (a console script, a `python -m` entry) is not measured. It
  is `missed` unless it is the `if __name__ == "__main__":` guard. Say which in-process test
  (calling `main([...])` directly) would cover it.
- Typically exempt: `if __name__ == "__main__":` guards, branches for another OS, and truly
  unreachable defensive branches.

## journey-test-writer
- Write one test function per journey step or command in `tests/journey/test_<command>.py`, named
  after what the user does (`test_count_prints_the_new_count`).
- Run the installed console script as a real subprocess (`subprocess.run([...], cwd=tmp_path,
  ...)`, with the script found by `shutil.which`). Never call `cli.main()` in-process: that would
  miss packaging and entry-point mistakes.
- Use `tmp_path` as the working directory; journeys never touch the repo.
- Assert on the exit code, stdout/stderr and files written, not on the wording of incidental log
  lines.
- Set up any environment variable or config file the command needs inside the test (a fixture).
- A journey that consumes a service part reads its address from `BULL_URL_<PART>` (bull starts
  the service and sets it). Don't skip when it is missing: fail with a message naming the
  variable.
