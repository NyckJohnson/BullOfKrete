---
description: "Build a stack (a language or platform bull can build apps with) in its own stack repo, stage by stage"
argument-hint: "[nothing; continues the stack in this repo]"
---

# Build a stack

A stack teaches bull a language or platform: how to build and test an app in it, how to read its
contracts and coverage, and the rules its agents follow. You build one in its own stack repo, stage
by stage, the way an app is built: design first, then the fixture and its cases, then the gate code,
then review and acceptance.

## 0. Refuse outside a stack repo

Run `bull status`. It must show a stack repo (kind stack). In an app, or in a folder with no
`.bull/`, stop and tell the human: a stack is built in its own folder, created with
`bull init --stack <path>` in a terminal and opened with `bull open <path>`.

## Rules of the workflow

- A stack repo's `bull status` has only `next`, `stage`, `checkpoint` and `ref`: usage-check,
  pause and resume are not available in a stack repo, and there is no plan gauge. Stop at a step
  boundary if the human asks you to.
- `bull stack test .` (and `--static`) records a pass only on a clean tree at HEAD. Commit the work
  before each run, commit each fix and run it again until it passes, and only then set the next
  stage.
- Commit after every step. Run each `bull status …` change before that step's commit, and tag after
  the commit.
- Move through stages and checkpoints only with `bull status stage <n>` and
  `bull status checkpoint <name>`. They refuse out of order; when one does, tell the human what is
  missing. `bull status next` names the next step.
- Tag each checkpoint with `git tag $(bull status ref tag <checkpoint>)`.
- The orchestrator's rules hold: one subagent at a time, briefs in the usual shape, and questions to
  the human as **Asking the human** describes. Briefs say `MODE: stack` and carry no module or unit
  lines. Attempts count as in Stage 5: after `max_attempts` failed attempts at a step, stop and ask
  the human.
- The **Stack files** section at the end of this command is the spec every brief points at. Each
  brief's `READ ONLY THESE:` starts with
  `.bull/plugin/commands/stack.md § Stack files` and `DESIGN.md`, then the files of the step.

## 1. Discuss

1. Read `DESIGN.md` (from `bull template design`). Settle every heading in it with the human:
   - **Language and tools**: the language version; how to build; the test framework; how to run one
     module's tests and how to rerun a single failed test; where coverage data comes from; the lint
     and format tools.
   - **Contracts**: what a contract is in this language, and how `contract_declarations` reads one.
   - **Modules**: how `Modules/<Module>/` with its `Contracts/` folder maps onto the language's
     normal project layout; where the module's mocks and view files go.
   - **Kind**: `app`, `service` or `tool`.
   - **Human setup**: what the human installs or creates by hand before the first build.
   - **Adoption support**: whether the stack can adopt existing projects now (`detect`) or later.
   - **Interfaces and running**: which interface formats it checks; for a service, how bull starts,
     waits for and stops it (`[run]`).
   - **Decisions log**: one line per decision.
2. Write the answers into `DESIGN.md` as you go, and commit.
3. ✋ Ask the human for explicit approval of `DESIGN.md`. Then:
   1. Run `bull status checkpoint design-approved`.
   2. Commit.
   3. Tag with `git tag $(bull status ref tag design-approved)`.

## 2. Scaffold

1. Run `bull status stage 2`.
2. Fill every `stack.toml` key with its real value from the design: no `TODO` left, and
   `maturity = "experimental"`.
3. Create `readers.py`, `rules.md` and `setup.md` as skeletons with the required functions and
   headings (see **Stack files**).
4. Commit.

## 3. Fixture and cases first

1. Run `bull status stage 3`.
2. Brief the **test-writer** with `MODE: stack`: it writes `fixture/` (a tiny one- or two-module app
   in this stack that passes every gate; only files bull can write, no hand-made project files unless
   the language needs them) and `cases.json` with every required case id.
3. Commit, then run `bull stack test . --static` on the clean tree. It checks the shape only; the
   gates are not written yet. Each failure goes back to the test-writer; commit each fix and run it
   again until it passes.

## 4. Gate code

1. Run `bull status stage 4`. It needs a static pass at HEAD.
2. Brief the **code-writer** with `MODE: stack`: it writes the gate program that the `[gates]` argv
   lists run, `readers.py` (`contract_declarations`, `test_results`, `uncovered`, `check`; and, as
   the design says, `detect`, `inventory`, `legacy_declarations`, `interface_check`), and
   `setup.md`, in this language's own idioms.
3. Commit, then run `bull stack test .`, which uses the real toolchain, on the clean tree until
   every case gives its expected verdict. A case that reports "not run" fails too: install what it
   names, with the human.
4. Failures go back to the code-writer, with attempts and blocked questions handled as in Stage 5.
   Commit each fix and run the test again.

## 5. Review

1. Run `bull status stage 5`. It needs a full test pass at HEAD.
2. Brief the **code-writer** with `MODE: stack` to write `rules.md` from the approved design:
   `## common`, then one `## <agent>` per entry in `agents`, then `## outline`.
3. Brief the **reviewer** with `SCOPE: stack`: it reviews the whole stack folder against the
   **Stack files** spec and `DESIGN.md`. Findings go back to the code-writer (attempts count). After
   any change, commit and run `bull stack test .` again on the clean tree.
4. ✋ Ask the human to review `rules.md` themselves: these rules shape every line the agents write.
   Revise until they approve. Then:
   1. Run `bull status checkpoint rules-approved`.
   2. Commit.
   3. Tag with `git tag $(bull status ref tag rules-approved)`.

## 6. Accept

1. Commit, then run `bull stack test .` on the clean tree. Every case must pass.
2. Run `bull status checkpoint accepted`, then `bull status stage 6`.
3. Commit.
4. Tag with `git tag $(bull status ref tag accepted)`.
5. Tell the human: `bull stack install <path>` makes the stack selectable, as `experimental`. It
   becomes `verified` after one real app is accepted with it.

## Stack files

This is the spec for a stack folder. Every brief in this workflow points here. A stack folder holds:
`stack.toml`, `readers.py`, `rules.md`, `setup.md`, `DESIGN.md`, `cases.json` and `fixture/`.

### stack.toml

The manifest. It starts with `format = 1`. No value may be `TODO`.

```toml
format = 1

[stack]
name = "<name>"            # lowercase letters, digits, _; starts with a letter; equals the folder name
title = "<title>"          # short human name
description = "<one line>"
language = "<language>"
kind = "tool"              # app | service | tool
maturity = "experimental"  # experimental | verified | test
source_glob = "<glob>"     # matches the language's source files, e.g. "*.<ext>"
test_glob = ["<glob>"]     # matches test files
comment = "<prefix>"       # line-comment prefix, used for coverage-exempt markers
scaffold = ["<folder>"]    # folders `bull stack select` creates in the app
gitignore = ["<line>"]     # lines merged into the app's .gitignore
agents = ["skeleton-builder", "test-writer", "code-writer", "reviewer", "coverage-analyst"]

[[stack.requires]]         # one table per tool the toolchain needs on PATH
tool = "<command>"
hint = "<where to get it>"

[settings.source_dir]      # required: where module code lives in a part
type = "str"
default = "<folder>"
description = "<one line>"

[settings.test_dir]        # required: where tests live
type = "str"
default = "<folder>"
description = "<one line>"

[gates]                    # argv lists
preflight = ["<program>", "<args>"]
setup = ["<program>", "<args>"]
build_test = ["<program>", "<args>"]
build_test_fast = ["<program>", "<args>", "{module}"]
lint = ["<program>", "<args>", "{module}"]
rerun_failed = ["<program>", "<args>", "{failed_ids}"]
journeys = ["<program>", "<args>"]        # optional

[run]                      # optional; service stacks
start = ["<program>", "{port}"]
ready = ["<program>", "{port}"]
stop = ["<program>", "{port}"]
ready_timeout = 30

[interfaces]               # optional
formats = ["json-schema"]

[commands]                 # optional extra commands for `bull stack run <name>`
<name> = ["<program>", "<args>"]
```

- `[stack]`: `name`, `title`, `description`, `language`, `kind`, `maturity`, `source_glob`,
  `test_glob`, `comment`, `scaffold`, `gitignore`, `agents`, and zero or more
  `[[stack.requires]]` tables (`tool`, `hint`), which `bull doctor`, `bull stack check` and
  `bull stack test` look for. A name of `_template` or a built-in stack's name is refused.
- `[settings.<key>]`: the stack's own settings, each with `type`, `default` and `description`.
  `source_dir` and `test_dir` are required. A stack may also give defaults for bull's own keys,
  such as `[settings."coverage.exclude"]` with `default = ["<glob>"]`.
- `agents`: the agents whose rules `rules.md` holds. Required: skeleton-builder, test-writer,
  code-writer, reviewer, coverage-analyst; plus journey-test-writer when `[gates] journeys` is set,
  and surveyor when `readers.py` defines `detect`. (screen-builder and legacy-test-scanner may be
  added.)
- `[gates]`: each value is an argv list bull runs as one step, never through a shell:
  - `preflight`: checks the toolchain is ready before anything else runs.
  - `setup`: prepares the part (installs dependencies and the like).
  - `build_test`: builds and runs the whole test suite with coverage, writing results and coverage
    data into `{results}`.
  - `build_test_fast`: builds and runs only `{module}`'s tests, without coverage.
  - `lint`: lint and format checks on `{module}`.
  - `rerun_failed`: reruns only the tests named in `{failed_ids}`.
  - `journeys` (optional): runs the journey tests.
- `[run]` (optional, service stacks): `start`, `ready` and `stop` argv lists and `ready_timeout` in
  seconds. bull runs `start` with a free port, polls `ready` every half second until it exits 0, and
  always runs `stop` afterwards.
- `[interfaces]` (optional): `formats`, the interface formats `interface_check` understands.
- `[commands]` (optional): extra named argv lists, run with `bull stack run <name>`.

**Placeholders** bull fills in any argv: `{python}` (the interpreter bull itself runs on, for gate
programs written as scripts it can run), `{stack_dir}` (this folder, installed), `{app_root}`,
`{part_root}`, `{results}` (the part's results folder, absolute), `{module}`, `{module_src}`,
`{module_tests}`, `{failed_ids}` (expands to one argument per failed test id) and `{port}`.

**Environment** for every step: `BULL_PART`, `BULL_PART_ROOT`, `BULL_APP_ROOT`, `BULL_RESULTS`,
`BULL_STACK_DIR`, `BULL_ADOPT_MODE` (`0` or `1`), `BULL_SCOPE_MODULE` (a module name or empty),
`BULL_SETTINGS` (the part's resolved settings as JSON) and, for journeys only, one
`BULL_URL_<PART>` per running service part.

**Results:** a step passes on exit 0; any other exit fails it. Each stdout line
`bull-fail: <label>` adds a failure label to the step. Exit 2 from `preflight` aborts the whole
run. With `BULL_ADOPT_MODE=1`, legacy code only has to build and pass its tests, while module code
keeps the full standard. The `build-warning` case checks that a warning in module code fails the
build.

### readers.py

Functions bull imports, loaded with its own interpreter as a package, so the file may import
sibling files relatively and import bull's stacks contracts from `bull.Modules.stacks.Contracts`
(`TestRun`, `CoverageData`, `CheckItem`, `Detection`, `Issue`, `IssueLevel`, `Role`).

Required:

- `contract_declarations(path) -> list[str]`: the public declarations of one contract source file,
  one string each, in a stable order and normalized form (multi-line signatures joined), so that
  `bull api` can diff them.
- `test_results(results) -> TestRun | None`: reads the test report in the results folder:
  `count` (tests run) and `failed` (ids of failed tests, in the form `rerun_failed` accepts). None
  when there is no report.
- `uncovered(part_root, sources, results) -> CoverageData`: for each source file, the line numbers
  of code lines not covered (`uncovered`), and the files with no coverage data at all (`no_data`).
- `check(part_root, settings, adopting) -> list[CheckItem]`: the part's setup checks, each with
  `ok`, `item` and `fix`; `adopting` is true while an adoption is active.

Optional:

- `detect(root) -> Detection`: recognizes an existing project in this stack: `confidence` (0 to 1),
  `summary`, `settings` to apply, and `issues` (each `block`, `fix` or `note`).
- `inventory(root, settings) -> str`: a listing of the project's files and types (not used by bull
  yet).
- `legacy_declarations(part_root) -> list[str]`: names of declarations still in legacy code; bull
  keeps the ones starting with `Legacy`.
- `interface_check(part_root, settings, interface_file, format, role, module) -> list[CheckItem]`:
  checks a module's side (provider or consumer) of an interface against its interface file.

### rules.md

The agents' coding rules: `## common`, then one `## <agent>` per entry in `agents`, then
`## outline` (the memo conventions the orchestrator follows). An agent reads `## common` plus its
own section. Name the language, file names, test framework, tools and conventions concretely.

### setup.md

The human's manual steps, in order, then `## For a feature` (steps a feature that adds or changes
setup needs). With `detect`, also `## For an adoption` (steps for bringing an existing project in)
and `## Final switch` (the step to the stack's full strictness when an adoption ends).

### DESIGN.md

The approved design: Language and tools, Contracts, Modules, Kind, Human setup, Adoption support,
Interfaces and running, Decisions log.

### cases.json

The stack's self-test, run by `bull stack test`:

```json
{
  "format": 1,
  "layout": {"app/": "."},
  "settings": {"source_dir": "<folder>", "test_dir": "<folder>"},
  "cases": [
    {"id": "clean", "run": ["gates", "<module>"],
     "expect": {"verdict": "pass", "recorded": true}},
    {"id": "failing-test",
     "change": {"replace": {"<test file>": "<a failing test>"}},
     "run": ["gates", "<module>"],
     "expect": {"verdict": "fail", "gate": "tests", "output": "<test name>"},
     "then": {"run": ["gates", "--failed"], "expect": {"verdict": "fail", "ran": 1}}}
  ]
}
```

- `format`: 1.
- `layout`: maps fixture folders to folders of a fresh app.
- `settings`: the settings the fresh app gets.
- `cases`: each with an `id`, an optional `change`, a `run`, an `expect` and an optional `then`:
  - `change`: `add` and `replace` (path → text) and `delete` (a list of paths), applied and
    committed before the run. A `replace` or `delete` of a path that doesn't exist fails the case.
    `"dirty": true` on the case leaves the change uncommitted.
  - `run`: a `bull` argument list (gates runs add `--json`).
  - `expect`: `verdict` (`pass` or `fail`), `gate` (the failing gate: `build`, `tests`, `lint`,
    `api`, `coverage`, `interface`, `journeys`), `output` (a substring of the failure labels or
    check items), `recorded` (whether the pass was recorded), `ran` (number of tests run). No other
    keys.
  - `then`: a follow-up case run in the same folder afterwards.
- Required ids: `clean`, `fast`, `no-tests`, `failing-test` (with `then`), `build-warning`, `lint`,
  `contract-change`, `uncovered`, `exemption`, `setup-broken`; plus `journey` and
  `journey-failing` when `[gates] journeys` is set; `interface-drift` when `[interfaces]` is set;
  `run-lifecycle` when `[run]` is set; `adopt-mode` when `readers.py` defines `detect`.

### fixture/

A tiny app in this stack, one or two modules, that passes every gate as it is. Each case copies it
into a fresh folder by `layout`, adds bull's own files, applies the case's `change` and runs it.
Use only files bull can write; no hand-made project files unless the language needs them.

Nothing in this spec is tied to a particular language; the stack's own files are.
