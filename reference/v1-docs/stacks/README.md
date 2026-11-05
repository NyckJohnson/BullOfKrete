# Stacks

A stack is everything the pipeline needs to know about one kind of app: how to build, test and
lint it, how to read its contracts and coverage, what the human sets up by hand, and the coding
rules each agent follows. The process (stages, memo, units, checkpoints, features, usage pauses,
merge guard) is the same for every stack.

An app picks its stack during `/discuss` (`ios-pipeline stack select <name>`); it is stored as
`STACK` in the app's `.pipeline/config.sh`.

An app can also have several **parts**, each with its own folder and stack
(`ios-pipeline part add <name> <stack> [--dir <folder>]`; design in `docs/stacks.md`). A part's
settings are in `.pipeline/parts/<part>.sh`, with paths relative to its folder; the stack's scripts
get that folder as `root` (`check`, `coverage`, `inventory`) and the part's settings as `config`.

| Stack | What it builds |
| --- | --- |
| `ios` | Native iPhone app: SwiftUI, Swift 6, Swift Testing, XCUITest (app, verified) |
| `python_cli` | Python 3.11+ CLI tool: `uv`, `pytest`/`coverage.py`, `ruff`, `mypy --strict` (tool, experimental) |

`stacks/_template/` is not a stack (it has no `stack.sh`, so `ios-pipeline stacks` never lists it):
it holds only the `DESIGN.md` discussion checklist and the `cases.json` shape that `/new-stack`
starts a new stack from. Every other file of a stack is written fresh for that language, from the
spec below — never copied from `_template` or from `ios`. `ios` stays in this list as the one
finished example to read for "what does this look like once it's done."

## A stack folder

| File | Used by | Contents |
| --- | --- | --- |
| `stack.sh` | `ios-pipeline stacks`, scanners, gates, hooks | Manifest: `STACK_TITLE`, `STACK_DESCRIPTION`, `STACK_REQUIRES`, `STACK_LANGUAGE`, `STACK_SOURCE_GLOB`, `STACK_COMMENT`, `STACK_SCAFFOLD`; `STACK_KIND` (`app` has UI tests, `service` runs as a process, `tool` neither — informational; see "UI tests" below for what actually decides whether they run), `STACK_MATURITY` (`experimental` or `verified`), `STACK_TEST_GLOB` (test files the code-writer may not edit, besides `APP_TEST_DIR`) |
| `defaults.sh` | all scripts | Stack defaults, between `workflow/defaults.sh` and the app's config |
| `config.sh` | `stack select` | Settings added to the app's config; must set `APP_SOURCE_DIR` and `APP_TEST_DIR` |
| `gitignore` | `stack select` | Lines merged into the app's `.gitignore` |
| `gates.sh` | `workflow/gates.sh` | Sourced in each part's own subshell, run from the part folder (`PART`, `PART_ROOT`; `RESULTS` is absolute). The gate steps: `stack_preflight`, `stack_setup_gate`, `stack_build_test`, `stack_build_test_fast`, `stack_lint`, `stack_rerun_failed`, and optionally `stack_ui_tests` (details below); during an adoption `ADOPT_MODE=1` asks them to hold only module code to the full standard |
| `contract.py` | `ios-pipeline api` | `SOURCE_GLOB` and `extract(path)`: the contract declarations in one file |
| `coverage.py` | `workflow/coverage.py` | `uncovered(root, sources, data)`: uncovered lines per file, and files without data |
| `check.py` | `stack check`, `/setup` | `check(root, config)`: `[(ok, item, fix)]` for the manual setup; `config["ADOPTING"]` is `"1"` during an adoption |
| `detect.py` | `stack detect` | Optional. `detect(root)`: `{confidence, summary, config, issues}` for an existing project being adopted; issues are `(level, item, fix)` with level `block`, `fix` or `note` |
| `setup.md` | `stack setup`, `/setup` | The manual steps, one at a time, plus a "For a feature" section |
| `rules.md` | `stack rules <agent>` | `## common` plus one section per agent and `## outline` for the memo |
| `lint/` | `gates.sh` | Default lint configs |
| `cases.json`, `fixture/` | `stack test` | The stack's self-test: a small app (`fixture/`, in folders `layout` maps into an app) and cases, each a change plus the verdicts the commands must give (format in `workflow/stack_test.py`). iOS: `stacks/ios/fixture/SETUP.md` makes its Xcode project once |

### Adoption

Adopting an existing app (`/adopt`, `docs/adopt.md`) is stack-neutral; the stack supplies:

| Where | What |
| --- | --- |
| `detect.py` | Finds the project, proposes config values, reports blocking and setup issues |
| `inventory.py` | `inventory(root, config)` and `report(data)`: legacy files, their types and references (`stack inventory`) |
| `contract.py` | Optional `legacy_declarations(path)`: `Legacy…` types declared in a file (`status adopt legacy`) |
| `check.py` | Honors `config["ADOPTING"]` (e.g. allows an older language mode until Stage 6) |
| `gates.sh` | Honors `ADOPT_MODE`: module code at full strictness, legacy code only builds and passes its tests; with `SCOPE_MODULE` set, `stack_build_test` may skip the other modules' unit tests |
| `setup.md` | `## For an adoption` (project steps for an existing project) and `## Final switch (adoption Stage 6)` |
| `rules.md` | The adoption terms: the clean-state launch option, the composition root, the final switch, UI technology per screen; plus `## surveyor` and what belongs in the app shell (`## outline`) |

`workflow/stack_support.py` has the same list in its docstring.

## Writing a stack's files (the full interface)

This is the spec `/new-stack` writes each file from: detailed enough that every file can be
authored for the new language on its own terms, without copying another stack's file and editing
it. Read `stacks/ios/` alongside it for one worked example of the *shape*; its Swift- and
Xcode-specific choices (regex-based contract scanning, `xcodebuild`, a simulator) are not part of
the interface — they're how one stack happened to meet it.

**`stack.sh`** — plain `KEY="value"` lines, read by both bash and Python. Required: `STACK_TITLE`,
`STACK_DESCRIPTION`, `STACK_REQUIRES` (what a human installs before `/setup`), `STACK_LANGUAGE`,
`STACK_SOURCE_GLOB` (glob `contract.py`/`coverage.py` read source files with), `STACK_COMMENT`
(line-comment prefix, for `coverage-exempt:` markers), `STACK_KIND` (`app`, `service` or `tool`),
`STACK_MATURITY` (`experimental` until a real app has shipped with it), `STACK_TEST_GLOB` (space-
separated patterns identifying test files, for the hook that keeps `code-writer` out of tests).
`STACK_SCAFFOLD` (space-separated folders created by `stack select`) may be empty.

**`defaults.sh`** — `KEY="value"` lines for anything an app may want to override in its
`.pipeline/config.sh` (thresholds, tool choices, exclusion patterns). May be empty.

**`config.sh`** — settings `stack select` appends to an app's (or part's) config. Must set
`APP_SOURCE_DIR` and `APP_TEST_DIR` (where `Modules/<Module>/` and its tests live), plus whatever
else the stack's other files read from config (a project file, a scheme, a module/package name).

**`gitignore`** — lines merged into the app's `.gitignore` on `stack select` (build output,
caches, local tool state).

**`gates.sh`** — sourced into `workflow/gates.sh`'s per-part subshell; see that file's header
comment for the full contract (the variables available: `ROOT`, `PART`, `PART_ROOT`, `RESULTS`,
`PIPELINE_HOME`, `STACK_HOME`, `FAST`, `ADOPT_MODE`, `SCOPE_MODULE`, `FAILED_TESTS`, and the helpers
`log`, `fail`, `module_src`, `module_tests`, `module_names`). Must define:

| Function | Contract |
| --- | --- |
| `stack_preflight` | Checks required tools, prepares anything a run needs (e.g. picks a test target). Non-zero exit aborts the whole run (`exit 2`), not just this gate. |
| `stack_setup_gate` | Project-level checks that must hold before building; call `fail "<label>"` for each problem, don't exit. |
| `stack_build_test` | Builds and runs every module's tests with coverage; set `COVERAGE_DATA` to what `coverage.py` needs; return 1 on any failure. **Must fail if zero tests ran** — a build that reports success having run nothing passes every module, which is worse than a real failure. Append failed test ids to `$FAILED_TESTS`, one per line, in whatever form `stack_rerun_failed` accepts. |
| `stack_build_test_fast <Module>` | Builds and runs only that module's tests, no coverage; same zero-tests rule; return 1 on failure. |
| `stack_lint <Module>` | Lint/format checks for the module's source and test files; `fail` per problem found. |
| `stack_rerun_failed <id>...` | Runs only the named tests (the ids `stack_build_test`/`_fast` wrote to `$FAILED_TESTS`); return 1 if any fail. |
| `stack_ui_tests` *(optional)* | Runs the app's end-to-end/journey tests. Define it only if the stack has a journey layer to test (an iPhone UI, a CLI run end to end, an API hit over HTTP); if absent, `gates --app-ui-tests` and the adoption journey step report "no UI tests" and skip cleanly. **Nothing branches on `STACK_KIND` for this** — definining the function is what turns journeys on. |

`fail` labels are what the human and the orchestrator read when something breaks, and what
`cases.json`'s `output` strings are checked against (see "Self-test" below) — word them so a
case's expected text is drawn from here, not invented separately in `cases.json`.

**`contract.py`** — `SOURCE_GLOB` (string) and `extract(path: Path) -> list[str]`: every non-private
declaration in one `Contracts/` file (protocols/interfaces and shared data types), as the language
actually writes them — this does not need to be a full parser, a line-based scanner is fine (see
`stacks/ios/contract.py`'s docstring), but it must handle the language's normal formatting for
those constructs. Optional `legacy_declarations(path) -> list[str]`: names of renamed legacy types
in a file (adoption only).

**`coverage.py`** — `uncovered(root: Path, sources: list[Path], data: Path) -> (dict[Path, list[int]], list[Path])`:
for each source file, which lines its test run didn't execute, plus which files the coverage tool
reported no data for at all (treated the same as uncovered — a file that never ran shouldn't pass
silently).

**`check.py`** — `check(root: Path, config: dict) -> list[tuple[bool, str, str]]`: `(ok, item, fix)`
for every manual setup step (tool installed, project file configured, language/strictness mode
set). Read `config["ADOPTING"]` to relax whatever an adoption's legacy code hasn't reached yet
(e.g. allow an older language mode until Stage 6).

**`detect.py`** *(optional, adoption only)* — `detect(root: Path) -> {"confidence": float, "summary": str, "config": dict, "issues": list[(level, item, fix)]}`, `level` one of `block` (adoption can't proceed), `fix` (a setup step will handle it) or `note`.

**`inventory.py`** *(optional, adoption only)* — `inventory(root, config) -> dict` and
`report(data) -> str`: a scan of legacy files, their top-level types, and which types each
references (`stack inventory`).

**`setup.md`** — the manual steps a human runs once, in order, plus `## For a feature` (what a
feature adds, if anything) and, for adoption support, `## For an adoption` and
`## Final switch (adoption Stage 6)`.

**`rules.md`** — `## common` (rules every agent in this stack follows) plus one `## <agent>`
section per agent that writes this stack's code, and `## outline` (memo conventions: file-naming,
protocol syntax, model conventions). Required agent sections: `skeleton-builder`, `test-writer`,
`code-writer`, `reviewer`, `coverage-analyst`. Add `screen-builder` only if the stack has a UI
layer screens are built against; add `ui-test-writer` whenever `gates.sh` defines `stack_ui_tests`;
add `surveyor` (and adoption terms generally) only if `detect.py` exists.

**`lint/`** — default lint/format configs, used when neither the app nor the part folder has its
own.

**`cases.json` and `fixture/`** — the stack's self-test (`ios-pipeline stack test <name>`); see
"Self-test" below for the required cases and `workflow/stack_test.py`'s docstring for the file
format. Prefer a fixture made of files the pipeline itself can write (plain source/config text) —
a hand-built, binary-ish project file (as iOS needs an Xcode project for) is fragile and should be
the exception, not the default, for a new stack.

## Self-test

`ios-pipeline stack test <name>` runs the fixture through real gates; it needs the stack's
toolchain installed. `ios-pipeline stack test <name> --static` checks the stack's *shape* instead —
required files exist, the manifest has no placeholder values left, `gates.sh` defines the required
functions, `cases.json` covers the required case ids, and `rules.md` has the required sections —
so it needs no toolchain and runs anywhere, including while the stack targets a toolchain this
machine doesn't have. `/new-stack` step 3 ("fixture and cases first") is done when `--static`
passes; step 4 ("write the stack") is done when the real `stack test` passes every case. Whether a
case's expected `output` text actually matches what the code produces (rather than being invented
by hand) is for that real run to find — write `cases.json`'s `output` strings from `gates.sh`'s
`fail` labels and `check.py`'s items as a matter of style, but `--static` can't check it, since
most of those messages are built from interpolated values (a module name, a count).

Required case ids, every stack: `clean`, `fast`, `no-tests`, `failing-test` (its `rerun` step),
`build-warning`, `lint`, `contract-change`, `uncovered`, `exemption`, `setup-broken`. Required only
if `gates.sh` defines `stack_ui_tests`: `journey`, `journey-failing`. `docs/stacks.md`'s self-test
table lists a few more cases for capabilities not built yet (`interface drift`, `run lifecycle`,
`adopt mode`) — add those when the stack actually has that capability.

## Adding a stack

Not something an app session improvises (every stack is planned work; see `ROADMAP.md`). Run
`/new-stack <name>` in the **pipeline repo**, never inside an app:

1. **`ios-pipeline stack new <name>`** scaffolds `stacks/<name>/stack.sh` (placeholders marked
   `TODO`) and copies in `_template/DESIGN.md`.
2. **Discuss and fill in `DESIGN.md`** — language/tools, how tests and coverage work, what a
   contract is in this language, module layout, `STACK_KIND`. The human approves it.
3. **Write the fixture and `cases.json`** (from `_template/cases.json`'s shape) until
   `stack test <name> --static` passes.
4. **Write `gates.sh`, `contract.py`, `coverage.py`, `check.py`, `setup.md`** until
   `stack test <name>` (the real one) passes every case.
5. **Write `rules.md`.** The human reviews it — it shapes every line the agents will write.
6. Add the stack to the table above as `experimental`, run the pipeline's own tests
   (`python3 -m unittest discover -s tests`), commit on a branch, open a PR.

`docs/stacks.md` has the full design; `.claude/commands/new-stack.md` (pipeline repo only) runs
these steps and can resume partway through from `DESIGN.md`'s checklist.
