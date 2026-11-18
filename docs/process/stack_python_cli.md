# stack_python_cli: source note

The content of the `python_cli` stack's Markdown (`rules.md`, `setup.md`, `DESIGN.md`), its lint
config and its fixture app, rewritten from v1's `stacks/python_cli/` (memo **v1 Markdown review**)
in `bull` terms and v2 formats. The memo's `stack_python_cli` section says *what* the module is;
this note says *what each file says*. test-writer and code-writer read this note, never the v1
files. Approved by the human like a memo section; changes after approval go through the decisions
log.

How to read it: §1 holds the rules every file follows. §2–§6 give each file's content, section by
section, in the order the file should have them. Wording is the code-writer's; every rule, step and
check listed here must be in the file, and nothing in §1.3 may be. §7 lists the choices this note
makes where v1 and the memo leave a gap.

Style: plain words, short sentences, second person to the agent in `rules.md` ("You …"),
imperative steps in `setup.md`. Commands, paths and settings in backticks. No emoji except the ✅/✗
that `bull stack check` itself prints.

## 1. Rules for every file

### 1.1 Names
| v1 | v2 |
| --- | --- |
| `ios-pipeline <cmd>` | `bull <cmd>` |
| `ios-pipeline stack test python_cli` | `bull stack test python_cli` |
| `ios-pipeline stack rules <agent>` | `bull stack rules <agent>` |
| `ios-pipeline api` | `bull api` |
| `gates <module> --fast`, `--failed` | `bull gates <module> --fast`, `bull gates --failed` |
| ui-test-writer, UI tests | journey-test-writer, journey tests |
| `APP_SOURCE_DIR`, `APP_TEST_DIR`, `APP_PACKAGE` | the `source_dir`, `test_dir` and `package` settings |
| `.pipeline/config.sh` | `.bull/config.toml` (`bull config set <key> <value>`) |
| `STACK_KIND="tool"` | `kind = "tool"` in `stack.toml` |
| `stack_build_test`, `stack_lint`, `stack_ui_tests` | the `build_test`, `lint`, `journeys` gate steps |
| `FAILED_TESTS` | the failed test ids (`bull gates --failed` reruns them) |
| `contract.py`, `coverage.py`, `check.py` | `readers.py` (`contract_declarations`, `uncovered`, `check`) |
| `/new-stack`, `stack new` | `/bull:stack`, `bull init --stack <path>` |
| "the shared driver hardcodes `Modules/`" | "bull's module convention: `<source_dir>/Modules/<module>/`, contract in `Contracts/`" |
| `### <Module>`, `MAX_FILES_PER_UNIT` | `### <module>`, `max_files_per_unit` |

### 1.2 Stack words are allowed
These files are stack-specific: `pytest`, `mypy`, `ruff`, `uv`, `coverage.py` and Python terms are
fine here (the banned-word list applies to bull's stack-neutral text, not to a stack's own files).

### 1.3 Never in any file
`ios-pipeline`, `.pipeline/`, `config.sh`, `stack.sh`, `gates.sh`, `ui-test-writer`, any v1 build
checklist, any absolute path, `shellcheck` (dropped, §7.4), and iOS comparisons ("the same way a
Swift compiler error is", "the Python-native equivalent of xccov", "a world smaller than Xcode's"):
each rule stands on its own.

## 2. rules.md

Title `# Python CLI stack: rules`. One line under it: `bull stack rules <agent>` prints `## common`
plus the agent's section; `bull stack rules outline` prints `## outline` only. Sections in this
order: `## common`, `## outline`, then one per agent in `stack.toml`'s `agents`:
`skeleton-builder`, `test-writer`, `code-writer`, `reviewer`, `coverage-analyst`,
`journey-test-writer` (no `surveyor`: the stack has no `detect`, §4).

### 2.1 common
- Python 3.11+; `from __future__ import annotations` at the top of every source file. File names
  `snake_case.py`.
- The app is one installable package, `<source_dir>` (default `src/<package>`). Modules are
  subpackages at `<source_dir>/Modules/<module>/` (`Modules` capitalized: bull's module
  convention, the same for every stack). Module names are lowercase.
- A module's contract is `Modules/<module>/Contracts/__init__.py` (`Contracts` capitalized, same
  reason): `typing.Protocol` classes, `@dataclass`es, `Enum`s, public functions and type aliases.
  Only public names (no leading `_`) count; `bull api` lists them with Python's `ast`, so
  reformatting doesn't change the contract, while a changed signature, field type or added/removed
  public member does.
- Mocks: `Modules/<module>/mocks/__init__.py` (lowercase), `Mock<Protocol>` classes other modules'
  tests import. Mocks are left out of coverage (`coverage.exclude` default `*/mocks/*`).
- A file imports another module's `Contracts` or `mocks` only, and only from modules its memo entry
  lists under `Depends on`. Python doesn't enforce this; review does.
- Tests: pytest, in `<test_dir>/<module>/test_<file>.py`. Journey tests:
  `<test_dir>/journey/test_<command>.py`.
- `mypy --strict` runs in the build gate: a type error fails the build, not lint.
- Lint is `ruff check` plus `ruff format --check`, with the app's own ruff config if it has one,
  else the stack's `lint/ruff.toml`. The `N` (naming) rules are off so the capitalized `Modules`
  and `Contracts` folders pass.
- No bare `except:`; catch specific exceptions. No mutable default arguments.
- Interfaces (json-schema): a module that provides or consumes an interface declares, in its
  `Contracts/__init__.py`, a `@dataclass` named after the schema's `title`, one field per schema
  property with the matching type: `string` → `str`, `integer` → `int`, `number` → `float`,
  `boolean` → `bool`, `array` → `list[...]`; a property not in `required` is `X | None`. `bull
  gates` checks both sides against the schema file.

### 2.2 outline
- Protocols in the memo are Python, fenced ```` ```python ````, `typing.Protocol` subclasses.
- Data models are `@dataclass(frozen=True)` unless the memo entry says why one must be mutable.
- `Files:` lines use `.py` paths relative to the module folder, e.g. `Contracts/__init__.py,
  mocks/__init__.py | counter.py`.
- The CLI's commands go under `## Commands`, each naming the module that implements it. Each user
  journey under `## User journeys` names the commands it runs; journey tests run them.
- The console script is wired in `<source_dir>/cli.py` (`main()`), outside `Modules/`: list it as
  app shell, not as a module file. It stays thin (parse arguments, call a module's contract, print).
- An interface a module provides or consumes is a dataclass in its `Contracts` (§2.1).

### 2.3 skeleton-builder
- `Contracts/__init__.py` holds the Protocols, dataclasses and enums exactly as the memo gives them.
- Stub method bodies: `raise NotImplementedError(f"{type(self).__name__}.<method>")`; in feature
  mode, `NotImplementedError(f"{type(self).__name__}.<method> (feature <slug>)")`.
- Mocks: `Mock<Protocol>` classes in `mocks/__init__.py`, returning realistic sample data and
  recording calls (a `calls: list[...]` attribute or per-method counters).
- One placeholder test per implementation file, `tests/<module>/test_<file>.py`, holding
  `def test_placeholder() -> None: ...`, so every module runs at least one test from the start.
- A Contracts or mocks file with only declarations (bodies `...` or `raise NotImplementedError`)
  has nothing for coverage to find and needs no marker.
- If `uv` is missing or `uv sync` fails (the preflight gate says so), don't repair the environment:
  list the `bull stack setup` steps under `MANUAL STEPS FOR HUMAN`.

### 2.4 test-writer
- One `test_<file>.py` per implementation file, in `tests/<module>/`. Name tests by behavior
  (`test_increment_adds_one`, not `test_1`).
- `@pytest.mark.parametrize` for input tables.
- `tmp_path` for anything touching the filesystem; never a fixed path or the repo's own folders.
- `bull gates <module> --fast` runs `pytest tests/<module>` alone: keep each module's tests
  runnable on their own (no fixtures that only exist when every module's tests run).
- Run `uv run ruff format` and `uv run ruff check --fix` on every test file you write before you
  return.

### 2.5 code-writer
- Depend only on the Protocols and dataclasses other modules expose in `Contracts/`; never import
  another module's implementation files or its `mocks/`.
- Raise specific, documented exception types. No bare `except:`, no `except Exception: pass`.
- Secrets come from environment variables or a config file outside the repo; never hardcoded or
  logged.
- Use `with` for files, sockets and subprocesses.
- Prefix implementation details with `_` unless another file in the module needs them; nothing
  outside `Contracts/` is public.
- Docstrings on every public declaration in `Contracts/__init__.py`, and on tricky logic.
- `cli.py` stays thin (§2.2); logic belongs in modules.
- Iterate with `bull gates --failed` (reruns the tests that just failed), then confirm with
  `bull gates <module> --fast`.

### 2.6 reviewer
- Error handling: no bare `except:`; nothing swallowed unless the spec says so.
- Security: no secrets in source, logs or committed files; subprocess calls use argument lists,
  never a shell string built from untrusted input.
- Typing: passing `mypy --strict` is not enough. Flag an `Any` hiding a real type, and a
  `# type: ignore` without a comment saying why.
- API design: a Protocol method that only makes sense for one implementation is a blocker.
- Style nits ruff would catch are not findings.
- A dataclass or Protocol whose methods have real bodies (beyond `...`/`raise
  NotImplementedError`) has logic that needs tests; it is not declaration-only.
- Imports across modules go through `Contracts`/`mocks` of declared dependencies only (§2.1).

### 2.7 coverage-analyst
- Markers are Python comments: `# coverage-exempt: <reason>` at the end of a line, or
  `# coverage-exempt-begin: <reason>` … `# coverage-exempt-end` around a block.
- A file under "Files without coverage data" never ran under test, or has no executable code.
  Classify it `missed` unless it is declaration-only; then add `# coverage-exempt-file: <reason>`
  in its first 10 lines.
- Code that runs only in a subprocess (a console script, a `python -m` entry) is not measured. It
  is `missed` unless it is the `if __name__ == "__main__":` guard: say which in-process test (call
  `main([...])` directly) would cover it.
- Typically exempt: `if __name__ == "__main__":` guards, branches for another OS, truly
  unreachable defensive branches.

### 2.8 journey-test-writer
- One test function per journey step or command in `tests/journey/test_<command>.py`, named after
  what the user does (`test_count_prints_the_new_count`).
- Run the installed console script as a real subprocess (`subprocess.run([...], cwd=tmp_path,
  ...)`, the script found with `shutil.which`), never `cli.main()` in-process: that would miss
  packaging and entry-point mistakes.
- Use `tmp_path` as the working directory; journeys never touch the repo.
- Assert on exit code, stdout/stderr and files written; not on the wording of incidental log
  lines.
- Set up any environment variable or config file the command needs inside the test (a fixture).
- A journey that consumes a service part reads its address from `BULL_URL_<PART>` (bull starts the
  service and sets it); skip nothing when it is missing: fail with a message naming the variable.

## 3. setup.md

Title `# Python CLI stack: setup`. Intro: manual steps once per app (or part), before
`/bull:skeleton`; replace `<package>` with the package name from the memo; afterwards
`bull stack check` must pass every item. Steps:

1. **Install `uv`** (https://docs.astral.sh/uv/getting-started/installation/). `uv` fetches a
   matching Python itself.
2. **Write `pyproject.toml`** at the part root (`bull stack select` creates folders and merges
   `.gitignore` lines; it doesn't write this file). The template, as v1 with two additions:
   `testpaths = ["tests"]` and `mypy_path = "src"`:
   ```toml
   [project]
   name = "<package>"
   version = "0.1.0"
   requires-python = ">=3.11"
   dependencies = []

   [project.scripts]
   <package> = "<package>.cli:main"

   [build-system]
   requires = ["hatchling"]
   build-backend = "hatchling.build"

   [tool.hatch.build.targets.wheel]
   packages = ["src/<package>"]

   [tool.pytest.ini_options]
   pythonpath = ["src"]
   testpaths = ["tests"]

   [tool.mypy]
   python_version = "3.11"
   strict = true
   mypy_path = "src"

   [dependency-groups]
   dev = ["pytest>=8", "pytest-cov>=5", "coverage[toml]>=7", "mypy>=1.11", "ruff>=0.6"]
   ```
   (`pytest-cov` is added because the build gate runs `pytest --cov`; v1's list lacked it.)
3. **Make the package importable**: `src/<package>/__init__.py` (empty) and `src/<package>/cli.py`
   with a `main()` that returns 0. The skeleton fills them in.
4. **Settings**: `bull config set package <package>`; `source_dir` (`src/<package>`) and
   `test_dir` (`tests`) if they differ from what `bull stack select` wrote.
5. **Sync once**: `uv sync` at the part root (creates `.venv/` and `uv.lock`). Commit
   `pyproject.toml` and `uv.lock`.
6. Run `bull stack check`: `uv` found, `pyproject.toml` present, the package imports, Python ≥ 3.11.

Note: `Modules/<module>/` and `tests/<module>/` are created as modules are built; nothing to do by
hand.

`## For a feature`: a feature that adds a third-party dependency runs `uv add <dependency>` at the
part root and commits `pyproject.toml` and `uv.lock`. Nothing else: a Python package has no
capabilities or extra targets to wire by hand.

No `## For an adoption` or `## Final switch` (no `detect`, §4).

## 4. DESIGN.md

The stackflow template's headings (`# Stack design` → here `# Python CLI stack: design`), filled
from v1's DESIGN.md:

- **Language and tools**: Python 3.11+; `uv` (venv, dependencies, running every tool; fetches
  Python); `pyproject.toml` with `hatchling`; pytest (`--fast`: `pytest tests/<module>`; reruns by
  pytest node id `tests/<module>/test_x.py::test_name`, which is the test id bull stores);
  coverage.py via `pytest --cov`, read back from `coverage json`; `ruff check` and `ruff format
  --check`; `mypy --strict` inside the build step. Requires: `uv` (`[[stack.requires]]`).
- **Contracts**: `Modules/<module>/Contracts/__init__.py`; `readers.contract_declarations` uses
  `ast` (a real parser: decorators, multi-line signatures, docstrings are handled; formatting
  doesn't matter). It lists top-level public classes (name, bases, `dataclass`/`Protocol`
  decorators), their public methods as `def name(args) -> ret`, dataclass fields `name: type`,
  enum members, public functions and type aliases; private names are skipped.
- **Modules**: the folder tree (source `src/<package>/Modules/<module>/{Contracts,mocks}/`,
  `<file>.py`; tests `tests/<module>/test_<file>.py`, journeys `tests/journey/`). `Modules` and
  `Contracts` are capitalized by bull's convention, importable as
  `<package>.Modules.<other>.Contracts`; `N` lint rules off for that reason; `mocks` lowercase is
  the stack's choice. `source_glob = "*.py"`, `test_glob = ["test_*.py", "*_test.py"]`.
- **Kind**: `tool`. Journeys run the installed console script as a subprocess in a temp folder and
  check exit code, output and files written.
- **Human setup**: install `uv`, write `pyproject.toml` from `setup.md`, `uv sync`; `bull stack
  check` verifies `uv` on PATH, `pyproject.toml`, the package imports, Python ≥ 3.11.
- **Adoption support**: none for now (no `detect`, `inventory` or `legacy_declarations`): no
  existing Python app to adopt yet, and detection built without one would guess.
- **Interfaces and running**: `[interfaces] formats = ["json-schema"]`, checked by
  `schema_check.py` (stdlib only) through `readers.interface_check`: the side's `Contracts` must
  declare a dataclass named after the schema `title`, with matching fields and types (§2.1); each
  mismatch is an item naming the field and the role. No `[run]` (a tool, not a service).
- **Decisions log** (v1's, reworded, plus v2's):
  - 2026-11-03: Python 3.11 floor, `uv`, `hatchling`; adoption support deferred.
  - 2026-11-03: contracts read with `ast`, not a line scanner.
  - 2026-11-03: `mypy --strict` in the build step, since a type error is a build failure.
  - 2026-11-03: capitalized `Modules`/`Contracts` (bull's convention); `N` lint rules off.
  - 2026-11-17: rebuilt for bull v2: gates in `gates.py`, readers in `readers.py`, json-schema
    interfaces, `pytest-cov` in the template, `shellcheck` dropped.

## 5. lint/ruff.toml

Used when the app has no ruff config of its own (no `[tool.ruff]` in `pyproject.toml`, no
`ruff.toml`/`.ruff.toml`):
```toml
target-version = "py311"
line-length = 100

[lint]
select = ["E", "F", "W", "I", "B", "UP"]
```
`N` is not selected (§2.1).

## 6. Fixture

`fixture/` holds the app every case copies (`cases.json` `layout` `{"app/": "."}`), mirroring the
fixture stack's shape:

- `app/docs/outline.md`: v1's fixture outline in the v2 memo format: Purpose (a counter the CLI
  can bump and print; it checks the python_cli gates' verdicts); `## User journeys` — 1.
  **Count** — runs `fixture_cli count` twice in a temp folder: prints `1`, then `2`, exit 0;
  `## Commands` — `fixture_cli count` (module `counter`); Constraints (stack `python_cli`,
  Python 3.11+, offline, no accounts, no third party); Build order `1. counter`; module
  `counter` (Files: `Contracts/__init__.py | counter.py`; Protocol `CounterStore` with
  `value() -> int`, `increment() -> int`; Behavior: a new counter's value is its start value
  (default 0); increment returns the count plus one, which value then returns); `## Interfaces`
  — `### Count`: `- File: interfaces/count.json (json-schema)`, `- Provider: app / counter`, no
  consumers.
- `app/pyproject.toml` per §3 with package `fixture_cli`, plus `app/uv.lock`.
- `app/src/fixture_cli/{__init__.py, cli.py}`, `app/src/fixture_cli/Modules/counter/`
  (`Contracts/__init__.py` with `CounterStore` and the dataclass `Count(value: int)`, and
  `counter.py`, storing the count in a file in the working folder).
- `app/tests/counter/test_counter.py`, `app/tests/journey/test_count.py`.
- `app/interfaces/count.json` (title `Count`, `properties: {value: {type: integer}}`, required
  `value`), `app/docs/api/counter.md` and `app/docs/api/interfaces/Count.md` matching (written
  with `bull api`).

`cases.json`: every required id (`clean`, `fast`, `no-tests`, `failing-test` with `then`,
`build-warning` (a mypy error, label `mypy <file>:<line>`), `lint`, `contract-change`,
`uncovered`, `exemption`, `setup-broken`) plus `journey`, `journey-failing` and `interface-drift`
(a `Count` field renamed, failing the `interface` gate naming the field).

## 7. Choices this note makes (for approval)

1. **`pytest-cov` added to the `pyproject.toml` template.** The memo's build step runs `pytest
   --cov`, which needs it; v1's list had only `coverage`. (Alternative: run `coverage run -m
   pytest` instead and keep v1's list.)
2. **Lint rule set** (§5): `E, F, W, I, B, UP`, line length 100. The memo only says "without `N`".
   (Alternative: ruff's defaults, `E4, E7, E9, F`, line length 88, which is what bull itself uses.)
3. **Interface type map** (§2.1): adds `number` → `float` and `array` → `list[...]` to the memo's
   list, matching the types it names (`float`, `list[...]`).
4. **`shellcheck` dropped.** v1 ran it on any `.sh` file in a module; the memo's lint step doesn't
   include it, and it would be a second required tool for a rare case.
5. **Fixture has one module**, as the memo says. `Consumers:` is optional in the memo's interface
   format, so `interface-drift` checks the provider side only (the fixture stack adds a consumer
   module `display`; this one doesn't need it).
6. **Journeys reading `BULL_URL_<PART>`** (§2.8) fail rather than skip when the variable is
   missing, so a broken service setup can't pass silently.
