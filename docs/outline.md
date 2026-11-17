# BullOfKrete outline

<!--
Built by pipeline v1 (`ios-pipeline`) with the python_cli stack. Module names are lowercase
(stack rule); each module is `src/bull/Modules/<module>/` with tests in `tests/<module>/`.
Read docs/bull-v2-brief.md first: its decisions are settled. docs/discussion-notes.md holds the
reasons behind the choices summarized here.
-->

## Purpose
BullOfKrete (`bull`) is version 2 of the agent pipeline: a Python command plus a Claude Code plugin
that builds software in six staged steps (discuss → outline → setup → skeleton → prototype → modules
→ verify), plus a feature cycle and adoption of existing apps, using specialized subagents,
automated gates and human checkpoints. It does everything v1 does, rewritten from this spec, with a
stack-neutral core: every platform (Python, iOS, shell, …) is a **stack**, a self-contained folder
of a TOML manifest, Python readers, agent rules and a self-test, and stacks themselves are built
through a staged workflow like apps. It is for developers who use Claude Code and want it to build
and extend apps through a disciplined, test-first, staged process in any language; it is
open-sourced (MIT) after v2.0 is accepted, so it must install and make sense for strangers.

## User journeys
Journeys run `bull` as a real subprocess (the installed console script) against temporary git
repos, the way the orchestrator and the hooks call it. Subagents are not part of the tests: where a
step is an agent's work, the test writes the files that agent would write. Apps in journeys use the
built-in **fixture stacks** (`fixture`, `fixture_service`; module `stack_fixture`) unless a journey
says otherwise. Hooks are driven by feeding `bull hook <name>` the JSON Claude Code would send.

1. **Install and init** — Dana, new to bull, wants a new app ready for `/bull:discuss`. She runs
   `bull doctor` (reports uv, git and claude found with versions; lists stacks and which toolchains
   are missing), then `bull init ~/apps/tally`: bull creates the folder, `git init` on `main`,
   `.bull/config.toml`, `.bull/status.json` at stage 0, `.bull/backlog.json`, `.gitignore`,
   `.claude/settings.json` and `CLAUDE.md`, and commits `chore: bull init`. `bull open ~/apps/tally
   --print-command` prints the `claude` command line it would launch with the plugin rendered from
   the installed package. Ends when `bull status` says stage 0, next `/bull:discuss`.
   - Failure path: `bull init` on a non-empty folder that isn't a bull app refuses (exit 1) and says
     why (and that `--adopt` exists); on an existing bull app it relinks (rewrites the provider
     files) without touching `.bull/status.json`, `backlog.json` or `config.toml`; inside a
     subfolder of an app it refuses before creating anything.
   - Failure path: `bull doctor` with `claude` missing from `PATH` exits non-zero and names the fix.
2. **Build a small app end to end** — Dana builds `tally` with the `fixture` stack: `bull stack
   select fixture`, stage changes 1→6, a memo with two modules (`Store`, then `Counter` depending on
   it), `bull status init-modules`, `bull stack check` passes → checkpoint and tag `setup`, skeleton
   gates pass → tag `skeleton`, checkpoint `ui-approved`; for each module: branch from `bull status
   ref module <M>`, unit states tests → code (after `gates <M> --fast` passes) → done, `bull gates
   <M> --coverage-report` clean, `bull gates <M>` records a pass, `git merge --no-ff`, `bull gates
   --after-merge <branch>` records without rerunning, `bull api <M> --write`, tag `module/<M>`; then
   `bull gates --all` and checkpoint `app-accepted` → tag. Ends when `bull status --json` shows every
   unit done and `bull status tags --json` lists every checkpoint and module tag.
   - Failure path: `bull status module Counter in_progress` before `Store` is done is refused, naming
     `Store`.
   - Failure path: a unit's 4th attempt (`bull status attempt Counter 1` after three) is refused and
     the unit is `blocked` until `bull status unblock Counter 1`.
3. **Pause on usage and resume** — mid-build the status line (`bull statusline`, fed Claude Code's
   status JSON) records 5-hour usage at 92%. `bull status usage-check` prints `PAUSE` with the reset
   time; `bull hook before-agent` blocks the next subagent launch with the same reason. Dana commits
   and runs `bull status pause "usage"`. In a fresh session, `bull hook session-start` prints the
   stage, the paused unit and "run `/bull:resume`"; usage is back at 10%, `usage-check` prints `OK`,
   `bull status resume` clears the pause. Ends when `bull status next` names the same unit.
   - Failure path: no usage data yet → `UNKNOWN` (exit 0) with a warning; agent launches are allowed.
4. **Features from a file; build one, abandon one** — after `app-accepted`, Dana writes `ideas.md`
   with three ideas and runs `bull feature import ideas.md`: three backlog entries, each with a brief
   in `docs/features/`. `bull feature start reset-button` commits on `main` and switches to
   `feature/reset-button/main`; she edits the memo to mark `Counter` with `Changes (reset-button)`
   and `Contract changes (reset-button)`; `bull feature plan` reopens only the unit holding the
   changed file. The unit runs the loop; the contract change passes `bull api Counter --write` as
   pre-approved; verify; `bull feature accept`; the merge to `main` and tag
   `feature/reset-button/accepted`. Meanwhile she queued a fourth idea on `main`; the merge has no
   conflict (separate backlog file). She starts `dark-mode`, changes her mind, and runs `bull feature
   abandon` on `main`. Ends when `main` has no `dark-mode` code and the backlog marks it abandoned.
   - Failure path: starting a second feature while one is active is refused; so is any feature
     before `app-accepted` and any feature during an adoption.
5. **Adopt an existing app** — Sam has a small app built without bull (fixture stack files and
   tests, a git repo with commits on `main`). `bull init --adopt .` detects the stack (the stack's
   `detect`), prints the detection report, writes the config, commits, records the adoption and
   switches to `adopt/main`. The memo lists one module with `Legacy files:`, `Legacy tests:` and
   `Callers to repoint:`; baseline journey tests pass against the app as it is → checkpoint and tag
   `adopt/baseline`; scaffold → `adopt/scaffold`. The module's last unit is the switch-over (`bull
   status next` names it): legacy files deleted, callers repointed; full gates with journey tests
   pass; merge into `adopt/main`. Ends when `bull adopt finish` records `adopted` and `app-accepted`
   and the app is an ordinary accepted app (`bull status --json` shows no adoption).
   - Failure path: `bull adopt finish` while a legacy file listed in the memo still exists is refused
     and lists the file.
6. **Add a stack through the stack workflow** — Lee wants a `go_cli` stack (in the test, files the
   test writes stand in for the agents' work). `bull init --stack ~/stacks/go_cli` creates a stack
   repo with `stack.toml` placeholders, `DESIGN.md` and its own status at stage 1. Checkpoint
   `design-approved` → tag `stack/design-approved`; scaffold; fixture and `cases.json` written;
   `bull stack test . --static` passes; gate code written; `bull stack test .`: every case gives its
   expected verdict; `rules-approved` → tag; `accepted`. `bull stack install ~/stacks/go_cli` makes
   it selectable. Ends when `bull stacks` lists `go_cli` as experimental.
   - Failure path: a gate that passes everything → the `failing-test` case reports the wrong verdict
     and `stack test` fails; a case whose tool is missing reports "not run" and also fails.
7. **An app with two parts** — Ana's app has `cli` (stack `fixture`) and `web` (stack
   `fixture_service`): `bull part add cli fixture --dir cli`, `bull part add web fixture_service
   --dir web`. Each module has a `Part:` line; `bull gates <M>` runs from its part folder with that
   part's stack; `setup` is recorded only when both parts pass `bull stack check --part <p>`; `bull
   gates --all` runs each part, then interfaces, then journeys. Ends when `--all` passes.
   - Failure path: a memo where a `web` module depends on a `cli` module is refused by
     `init-modules`; overlapping part folders are reported by `bull part check`.
   - Interface: the memo's `## Interfaces` names `interfaces/tally-events.json` (json-schema),
     provider `cli / Export`, consumer `web / Import`. `bull api --interface TallyEvents --write`
     snapshots it; the `interface` gate checks each side with its own stack; `web / Import` is built
     and gated before `cli / Export` exists. Before a journey that crosses parts, bull starts the
     `web` part (start/ready), passes its address, and stops it afterwards even when the journey
     fails, leaving no process.
   - Failure path: the provider declares a field the schema doesn't have → the `interface` gate fails
     on the provider side; editing the interface file fails the `api` gate until approved.
8. **A contract change stops the pipeline** — during `Counter` unit 2 a contract declaration in
   `Counter/Contracts/` changes. `bull gates Counter --fast` fails the `api` gate with a diff against
   `docs/api/Counter.md`. The orchestrator runs `bull status wait Counter "contract change"`;
   `bull status next` reports the wait and `bull hook before-agent` blocks agent launches. Dana
   approves: `bull status approve Counter "<note>"` logs the decision; `bull api Counter --write`
   updates the snapshot; gates pass. Ends when `next` names the unit again.
   - Failure path: `bull api Counter --write` without an approval is refused.
   - Variant: inside a feature whose memo lists `Contract changes (<slug>)` for `Counter`, the write
     passes without an approval once; a further change after that still needs one.
9. **An unverified merge is blocked** — Dana (or the orchestrator) runs `git merge --no-ff
   module/Counter` on `main` after only `gates --fast`. `bull hook before-shell` refuses: no recorded
   full pass for the branch head. After `bull gates Counter` passes on a clean tree, the same merge
   is allowed. Ends when the merge goes through.
   - Failure path: a dirty working tree makes `bull gates Counter` pass without recording, and says
     why.
10. **Settings** — Dana runs `bull config set max_attempts 5` in her app; `bull config show` lists
    `max_attempts = 5 (app)`, `review_mode = combined (bull default)` and `models.reviewer` from her
    user layer (`~/.config/bull/config.toml`). Ends when `bull status attempt` allows a 4th attempt.
    - Failure path: `bull config set max_attempts many` is refused with the expected type; a
      hand-edited `config.toml` with an unknown key makes `bull status` fail naming the file, line and
      key.
11. **Format versions** — an app whose `.bull/status.json` has a newer `format` than the installed
    bull: every `bull` command in it (except `doctor` and `--version`) stops with "this app's files
    are format 2; this bull reads format 1: upgrade bull". `bull migrate` on a current app says
    "already format 1" and commits nothing. Ends when commands work again after the file is restored.
    (Migrating an older format is unit-tested with a registered test migration: v2.0's format 1 is
    the first.)
12. **Reference tests for a rewrite** — Dana rewrites an old tool with bull. Her memo gives module
    `Store` a `Reference tests:` line naming two old test files and lists one old test under `##
    Unmapped reference tests` with a reason. After `Store`'s last unit, `bull status next` names the
    reference-test scan before coverage triage; `bull status refscan Store --covered 3 --missed 1`
    records it. Ends when the merge of `module/Store` is allowed.
    - Failure path: before the scan is recorded, `bull hook before-shell` blocks the merge of
      `module/Store`, naming the scan.
    - Failure path: `bull hook before-agent` launching `bull:test-writer` or `bull:code-writer` with a
      prompt that mentions the reference folder is blocked; so is a `Read` by those agents inside it.

## Screens and navigation
- No screens: bull is a command-line tool and a Claude Code plugin. Its user-facing surfaces are the
  `bull` command (see **Commands**) and the plugin's slash commands (`/bull:discuss`, `/bull:outline`,
  `/bull:setup`, `/bull:skeleton`, `/bull:prototype`, `/bull:build`, `/bull:verify`,
  `/bull:adopt`, `/bull:feature`, `/bull:resume`, `/bull:status`, `/bull:stack`), whose text the
  `plugin_text` module holds. Stage 4 (prototype) is skipped for this tool (see decisions log); the
  command surface is first checked by the cli module's tests and the Stage 6 journey tests.

## Commands
Each command is wired in the named module's `cli.py`; the `cli` module composes them. Every command
takes `--help`; the ones marked *json* take `--json`. Every command run inside an app folder first
checks file formats (module `formats`) and settings (module `settings`).

| Command | Does | Module `cli.py` |
| --- | --- | --- |
| `bull init [path] [--adopt] [--stack]` | New app, relink, adoption start, or stack repo | appinit |
| `bull open [path] [--print-command] [-- <claude args>]` | Render the plugin, launch Claude Code | appinit |
| `bull doctor` *json* | Check install and toolchains | appinit |
| `bull status` *json* (summary), `status next`, `status stage <n>`, `status checkpoint <name>`, `status init-modules [--replace]`, `status module <M> <state>`, `status unit <M> <n> <state>`, `status attempt <M> <n>`, `status unblock <M> <n>`, `status pause "<reason>"`, `status resume`, `status wait <M> "<what>"`, `status approve <M> "<note>"`, `status refscan <M> --covered n --missed n --contradicts n --not-in-spec n`, `status plan <label> <item>… / --clear`, `status tick <item>`, `status ref trunk|base|module <M>|tag <label>`, `status tags` *json* | Pipeline state | status |
| `bull status usage-check` *json* | OK / PAUSE / UNKNOWN | status (uses `usage`) |
| `bull feature add "<Title>: <desc>" [--top]`, `import <file> [--section <heading>] [--dry-run]`, `list` *json*, `move <slug> <pos>`, `drop <slug>`, `start [<slug>]`, `plan`, `accept`, `abandon` | Backlog and feature cycle | features |
| `bull adopt start`, `legacy` *json*, `finish`, `abandon` | Adoption | adoption |
| `bull stack detect [--apply [<stack>]]` *json* | Detection report for an existing project | adoption |
| `bull gates <M> [--fast\|--coverage-report\|--skip-coverage]`, `--failed`, `--all [--skip-coverage]`, `--after-merge <branch>`, `--journeys` (all *json*) | Gates | gates |
| `bull coverage <M>` *json* | Triage report from the last full run's data | gates |
| `bull api <M> [--write [--approved "<note>"]] [--check]`, `bull api --interface <Name> [...]` | Contract snapshots | api |
| `bull stacks [--all]` *json*; `bull stack select <name>`, `rules <agent> [--part p]`, `setup [--section s] [--part p]`, `check [--part p]` *json*, `run <command> [--part p]`, `install <path>` | Stacks | stacks |
| `bull stack test <name\|path> [--static] [--case <id>]` *json* | Stack self-test | stacktest |
| `bull part add <name> <stack> [--dir <folder>]`, `part list` *json*, `part check` | Parts | parts |
| `bull config show [--part p]` *json*, `bull config set <key> <value> [--user\|--part p]` | Settings | settings |
| `bull migrate` | Upgrade the app's files to the current format | formats |
| `bull template outline\|backlog\|design` | Print a template | memo (design: stackflow) |
| `bull hook <session-start\|before-agent\|before-shell\|before-edit\|before-read\|agent-end>` | Hook entry points (stdin JSON from the provider) | hooks (I/O: claude_code) |
| `bull statusline` | Status line: record usage, print the line | claude_code |
| `bull help`, `bull --version` | | cli |

In a stack repo (`bull init --stack`), `bull status` and `status stage|checkpoint|next|ref` act on
the stack workflow (module `stackflow`); other app commands refuse with "this is a stack repo".

## Constraints
- Stack: python_cli (one part). Package and console script `bull` (`APP_PACKAGE="bull"`,
  `APP_SOURCE_DIR="src/bull"`, `APP_TEST_DIR="tests"`; set in `.pipeline/config.sh` during
  `/setup`). PyPI distribution name `bullofkrete` (`bull` is taken; settled in `/setup`).
- App shell (not a module): `src/bull/__init__.py` (`__version__`), `src/bull/__main__.py`
  (`python -m bull` → `bull.Modules.cli.main.main`); console script `bull =
  "bull.Modules.cli.main:main"`. Written by skeleton-builder.
- Composition root: `bull.Modules.cli.wiring` is the only file that imports other modules'
  implementation files; every other file uses other modules only through their `Contracts` (and
  tests through `mocks`). Modules receive collaborators as constructor arguments typed by protocol.
- Built-in stacks are folders `src/bull/Modules/stack_*/<stack name>/` holding `stack.toml`. Their
  `fixture/` and `app/` folders are test data: excluded from bull's own mypy, ruff, pytest
  collection and coverage (configured in `pyproject.toml` during `/setup`).
- Python 3.11+ (stdlib `tomllib`); uv for install and development. No runtime dependencies beyond the
  standard library (none is justified in v2.0).
- macOS and Linux; the iOS stack needs macOS with Xcode. Paths go through `pathlib` and the
  `foundation` layout helper; no shell strings (`subprocess` with argument lists only) so Windows
  can come later without rework.
- Needs git and Claude Code on the user's Claude plan; never uses an API key or pay-as-you-go usage.
- Offline: yes. Accounts: none. Sync: none. No server or network service of its own (the only
  network listener is a fixture service part bound to 127.0.0.1 during tests).
- Third-party: none at runtime. Development: pytest, coverage.py, ruff, mypy (python_cli stack).
- Every file bull writes in an app is written atomically (temp file + rename) and carries a `format`
  version; committed state is JSON (written only by bull) or TOML (human-edited, validated).
- Everything Claude Code-specific (plugin files' rendering, hook JSON, status-line JSON, launching,
  model names) lives in `claude_code`; the core speaks neutral types (`hooks`, `usage` contracts).
- Nothing outside `Modules/stack_*` names a language, toolchain or platform (checked by a test in
  `cli`; banned words listed there).
- License MIT. README, CONTRIBUTING, LICENSE and the user and stack-author guides are written in
  Stage 6 (see Decisions log).

## Out of scope
- Reading v1 app files or formats automatically: only three v1 apps; migrated by hand
  (`bull-v1-migration.md`).
- Changes to v1 beyond bug fixes: v1 is frozen from memo approval on.
- Adopting a multi-part app: not needed yet; adoption of one-part apps comes first.
- Splitting a part into its own app: not needed yet.
- Interfaces shared between apps (an interface whose provider is another app): needs a way to point
  at another repo's file; not needed yet.

## Later features
- Windows support: hooks, paths and git behave differently; macOS and Linux first. v2.0 avoids needless POSIX-only assumptions.
- Phone notifications: send pipeline updates (paused, blocked, waiting for approval, module done) to the user's phone. Wanted soon after v2.0; first feature that needs a network service.
- GUI: a view across all apps, reading `--json` output (roadmap item 3); native macOS app or local web dashboard is open.
- Time report: `bull status time` totals by stage, module, unit, agent and gate step, from the event log (roadmap item 4). Before it ships, reading the log must survive a torn non-UTF-8 write: today foundation's strict `read_text` makes `EventLog.read` fail on the whole file instead of skipping the damaged line (found in events review, 2026-11-08).
- Settings page: GUI or screen for settings, beyond `bull config show/set` (roadmap item 5).
- Other AI providers: implementations behind the provider seam (roadmap item 6).
- Service stack: a stack whose part runs as a service (e.g. a Python HTTP service), giving OpenAPI interfaces and running parts together their first real stack.
- Store readiness: optional stack release hook plus the iOS checks (privacy manifest, icons, permission strings, store-guidelines review) (roadmap item 7).
- Token report: tokens per stage, module, unit and agent (roadmap item 8).
- Automatic orchestrator restarts at module boundaries: bull drives `claude` from outside; needs its own design.
- Quieter iOS test runs (in limbo): remaining experiments: shut down simulators after every run, report orphaned simulators at start, keep screenshots out of Photos and Spotlight; open questions on clean-state launches and the speed cost of no parallel testing (roadmap item 2).
- python_cli adoption support: `detect`/`inventory` for adopting existing Python apps (journey 5 uses the fixture stack).
- bash_shell stack: rebuilt through the stack workflow after Stage 6 (see Decisions log); moves here for good if it isn't done when the rest of v2.0 is.

## Data models
In-memory types are `@dataclass(frozen=True)` and enums in each module's `Contracts` (see the
protocol drafts under **Modules**). This section fixes the **file formats** bull reads and writes;
they are v2's own (no v1 compatibility). All JSON is UTF-8, `indent=2`, keys sorted, trailing
newline, written atomically. Times are ISO 8601 UTC with `Z`.

### App folder
| Path | Committed | Written by | Contents |
| --- | --- | --- | --- |
| `.bull/config.toml` | yes | human, `bull config set`, `stack select`, `part add` | app layer settings; `format = 1` |
| `.bull/parts/<part>.toml` | yes | human, `part add`, `config set --part` | part layer: `format`, `stack`, `dir`, the stack's settings |
| `.bull/status.json` | yes | `bull` only | pipeline state (below) |
| `.bull/backlog.json` | yes | `bull` only | feature queue (below) |
| `.bull/usage.json` | no | `bull statusline` | latest usage sample |
| `.bull/events.jsonl` | no | every state change, gate step, agent hook | event log |
| `.bull/passes/<sha>.json` | no | full gate runs | gate-pass records |
| `.bull/results/<part>/` | no | gates | stack results, coverage data, `failed.txt` (one test id per line) |
| `.bull/plugin/` | no | `bull open` | rendered plugin and orchestrator instructions |
| `docs/outline.md` | yes | orchestrator | the memo |
| `docs/api/<Module>.md`, `docs/api/interfaces/<Name>.md` | yes | `bull api --write` | snapshots |
| `docs/features/<slug>.md` | yes | `bull feature add/import`, orchestrator | feature briefs |
| `interfaces/` | yes | orchestrator / agents | interface files |

Machine-local `.gitignore` lines bull adds: `.bull/usage.json`, `.bull/events.jsonl`,
`.bull/passes/`, `.bull/results/`, `.bull/plugin/`, `.bull/run/`.

### status.json
| Field | Type | Notes |
| --- | --- | --- |
| format | int | 1 |
| kind | str | `"app"` (a stack repo has `"stack"`, see stackflow) |
| stage | int | 0–6 for the app's own track |
| checkpoints | list[str] | app track: `outline-approved`, `setup`, `skeleton`, `ui-approved`, `app-accepted` |
| modules | list[Module] | build order |
| pause | {reason: str, since: time, unit: str \| null} \| null | |
| waiting | {module: str, what: str, since: time} \| null | contract change awaiting approval |
| approvals | list[{module: str, note: str, time: time}] | unconsumed contract approvals |
| plan | {label: str, items: list[{name: str, done: bool}]} \| null | progress gauge |
| feature | {slug: str, stage: int, checkpoints: list[str], applied_contracts: list[str]} \| null | active feature |
| adoption | {stage: int, checkpoints: list[str]} \| null | active adoption; checkpoints `outline-approved`, `setup`, `baseline`, `scaffold`, `adopted` |

Module: `{name: str, part: str, depends: list[str], state: "pending"|"in_progress"|"done"|"blocked",
reference_tests: bool, scan: null | {time, covered: int, missed: int, contradicts: int,
not_in_spec: int}, units: list[Unit]}`.
Unit: `{number: int, files: list[str], kind: "code"|"switch-over", state:
"pending"|"tests"|"code"|"done"|"blocked", attempts: int}` (attempts starts at 1: the attempt in
progress).

### backlog.json
| Field | Type | Notes |
| --- | --- | --- |
| format | int | 1 |
| items | list[Item] | queue order |

Item: `{slug: str, title: str, description: str, state: "queued"|"active"|"accepted"|"abandoned"|"dropped",
added: time, brief: str}` (`brief` = `docs/features/<slug>.md`).

### config.toml (all layers)
Flat keys; dotted keys (`models.reviewer = "sonnet"`) or tables (`[models]`) both accepted.

| Key | Type | Default (layer) | Layers allowed |
| --- | --- | --- | --- |
| format | int | 1 | every file (not a setting) |
| base_branch | str | `main` (bull) | user, app |
| review_mode | choice combined\|split | `combined` | all |
| max_attempts | int ≥ 1 | 3 | all |
| max_files_per_unit | int ≥ 1 | 4 | all |
| usage.pause_5h | int 1–100 | 85 | user, app |
| usage.pause_weekly | int 1–100 | 95 | user, app |
| coverage.exclude | list[str] (globs) | from the stack | stack, app, part |
| coverage.exclude_extra | list[str] | `[]` | app, part |
| reference_dir | str | `reference` | app |
| bookkeeping_paths | list[str] | `[".bull/", "docs/"]` | app |
| models.<agent> | str | `sonnet` for test-writer, reviewer, coverage-analyst, journey-test-writer, surveyor, legacy-test-scanner; `inherit` for the rest | user, app |
| stack | str | — | app (one-part), part |
| dir | str | `.` | part |
| *stack keys* | per the stack's `[settings]` | stack | stack, app, part; every stack declares `source_dir` and `test_dir` |

Layer order (later wins): bull default → stack → user (`$XDG_CONFIG_HOME/bull/config.toml`, else
`~/.config/bull/config.toml`) → app (`.bull/config.toml`) → part (`.bull/parts/<part>.toml`).

### usage.json
`{format: 1, time, five_hour: float|null, weekly: float|null, five_hour_resets: time|null,
weekly_resets: time|null}` (percentages 0–100).

### events.jsonl
One JSON object per line: `{time, kind, ...data}`; kinds `status`, `gate_step`, `agent_start`,
`agent_end`, `hook_block`, `pause`, `resume`, `decision`. Data values are str, int, float, bool or
null.

### Gate-pass record (`.bull/passes/<sha>.json`)
`{format: 1, sha, branch: str|null, command: str, time, parts: list[str]}`.

### stack.toml (a stack folder's manifest)
```toml
format = 1
[stack]
name = "python_cli"            # ^[a-z][a-z0-9_]*$, not "_template"
title = "Python CLI tool"
description = "…"
language = "python"
kind = "tool"                  # app | service | tool
maturity = "experimental"      # experimental | verified | test (test: hidden unless `stacks --all`)
source_glob = "*.py"
test_glob = ["test_*.py", "*_test.py"]
comment = "#"                  # line-comment prefix for coverage-exempt markers
scaffold = ["src", "tests"]    # folders `stack select` creates (relative to the part folder)
gitignore = [".venv/", "__pycache__/"]
agents = ["skeleton-builder", "test-writer", "code-writer", "reviewer", "coverage-analyst", "journey-test-writer"]
[[stack.requires]]             # tools `doctor`, `stack check` and `stack test` look for
tool = "uv"
hint = "https://docs.astral.sh/uv/getting-started/installation/"
[settings.source_dir]          # the stack's settings: type, default, description
type = "str"
default = "src/myapp"
description = "…"
[settings.test_dir]
type = "str"
default = "tests"
description = "…"
[settings."coverage.exclude"]  # a stack may give defaults for bull's own keys
default = ["*/mocks/*"]
[gates]                         # argv lists; placeholders below; journeys optional
preflight = ["{python}", "{stack_dir}/gates.py", "preflight"]
setup = ["{python}", "{stack_dir}/gates.py", "setup"]
build_test = ["{python}", "{stack_dir}/gates.py", "build-test"]
build_test_fast = ["{python}", "{stack_dir}/gates.py", "build-test-fast", "{module}"]
lint = ["{python}", "{stack_dir}/gates.py", "lint", "{module}"]
rerun_failed = ["{python}", "{stack_dir}/gates.py", "rerun", "{failed_ids}"]
journeys = ["{python}", "{stack_dir}/gates.py", "journeys"]
[run]                           # optional (service stacks)
start = ["…", "{port}"]
ready = ["…", "{port}"]
stop = ["…", "{port}"]
ready_timeout = 30
[interfaces]                    # optional
formats = ["json-schema"]
[commands]                      # optional extra commands for `bull stack run <name>`
prune = ["{python}", "{stack_dir}/gates.py", "prune"]
```
Placeholders: `{python}` (bull's interpreter), `{stack_dir}`, `{app_root}`, `{part_root}`,
`{results}` (the part's results folder, absolute), `{module}`, `{module_src}`, `{module_tests}`,
`{failed_ids}` (expands to one argument per id), `{port}`. Environment for every step:
`BULL_PART`, `BULL_PART_ROOT`, `BULL_APP_ROOT`, `BULL_RESULTS`, `BULL_STACK_DIR`, `BULL_ADOPT_MODE`
(`0`/`1`), `BULL_SCOPE_MODULE` (module or empty), `BULL_SETTINGS` (the part's resolved settings as
JSON), `BULL_URL_<PART>` (journeys only, one per running service part). A step passes on exit 0;
a non-zero exit fails it; each stdout line `bull-fail: <label>` adds a failure label; exit 2 from
`preflight` aborts the whole run.

A stack folder also holds `readers.py` (Python functions bull imports; may import sibling files
relatively and `bull.Modules.stacks.Contracts`), `rules.md` (`## common`, one `## <agent>` per
entry in `agents`, `## outline`), `setup.md` (steps, then `## For a feature`, and with `detect`
`## For an adoption` and `## Final switch`), `DESIGN.md`, `cases.json`, `fixture/`.

### cases.json (a stack's self-test)
```json
{
  "format": 1,
  "layout": {"app/": "."},
  "settings": {"source_dir": "src/fx", "test_dir": "tests"},
  "cases": [
    {"id": "clean", "run": ["gates", "counter"],
     "expect": {"verdict": "pass", "recorded": true}},
    {"id": "failing-test", "change": {"replace": {"tests/counter/a.test": "fail one\n"}},
     "run": ["gates", "counter"], "expect": {"verdict": "fail", "gate": "tests", "output": "one"},
     "then": {"run": ["gates", "--failed"], "expect": {"verdict": "fail", "ran": 1}}}
  ]
}
```
`layout` maps fixture folders into a fresh app; `change` has `add`/`replace` (path → text) and
`delete` (paths); `run` is a `bull` argument list (gates runs add `--json`); `expect` keys:
`verdict` (`pass`/`fail`), `gate` (the failing gate), `output` (substring of the failure labels or
check items), `recorded` (bool), `ran` (tests run). Required ids: `clean`, `fast`, `no-tests`,
`failing-test` (with `then`), `build-warning`, `lint`, `contract-change`, `uncovered`,
`exemption`, `setup-broken`; plus `journey`, `journey-failing` when `[gates] journeys` is set;
`interface-drift` when `[interfaces]` is set; `run-lifecycle` when `[run]` is set; `adopt-mode`
when `readers.py` defines `detect`.

## Build order
1. foundation (depends on: none)
2. gitrepo (depends on: foundation)
3. events (depends on: foundation)
4. settings (depends on: foundation)
5. formats (depends on: foundation, gitrepo)
6. memo (depends on: foundation)
7. usage (depends on: foundation, settings)
8. stacks (depends on: foundation, settings)
9. parts (depends on: foundation, settings, stacks)
10. status (depends on: foundation, gitrepo, events, settings, memo, parts)
11. features (depends on: foundation, gitrepo, memo, status)
12. coverage (depends on: foundation, stacks)
13. api (depends on: foundation, memo, stacks, parts, status)
14. interfaces (depends on: foundation, settings, memo, stacks, parts, api)
15. adoption (depends on: foundation, gitrepo, settings, memo, stacks, parts, status, features)
16. gates (depends on: foundation, gitrepo, events, settings, memo, stacks, parts, status, coverage, api, interfaces)
17. stacktest (depends on: foundation, gitrepo, stacks)
18. stackflow (depends on: foundation, gitrepo, stacks, stacktest)
19. hooks (depends on: foundation, gitrepo, events, settings, memo, usage, stacks, parts, status, gates)
20. plugin_text (depends on: none)
21. claude_code (depends on: foundation, settings, usage, hooks, plugin_text)
22. appinit (depends on: foundation, gitrepo, settings, formats, stacks, status, adoption, stackflow, claude_code)
23. cli (depends on: foundation, gitrepo, events, settings, formats, memo, usage, stacks, parts, status, features, coverage, api, interfaces, adoption, gates, stacktest, stackflow, hooks, plugin_text, claude_code, appinit)
24. stack_fixture (depends on: stacks)
25. stack_python_cli (depends on: stacks)
26. stack_ios (depends on: stacks)

(The three stack modules depend only on `stacks`; they come last because each one's self-test runs
`bull stack test` end to end, which needs the whole command.)

## Modules

### foundation
- Purpose: errors, the app's file layout (the one place paths are built), atomic file I/O, the
  process runner and the clock, so everything else is testable with fakes.
- Depends on: none
- Files: Contracts/__init__.py, mocks/__init__.py | layout.py, files.py, runner.py, clock.py
- Protocol (draft; lives in `Contracts/`):
  ```python
  class BullError(Exception):
      """An error bull reports to the user: what went wrong and, when known, how to fix it."""
      def __init__(self, message: str, fix: str = "") -> None: ...
      message: str
      fix: str

  class ToolMissing(BullError): ...        # an executable isn't on PATH
  class FileFormatError(BullError): ...    # unreadable JSON/TOML; message names the path

  @dataclass(frozen=True)
  class AppLayout:
      root: Path; bull_dir: Path; config_file: Path; parts_dir: Path; status_file: Path
      backlog_file: Path; usage_file: Path; events_file: Path; passes_dir: Path
      results_dir: Path; plugin_dir: Path; run_dir: Path; memo_file: Path; api_dir: Path
      features_dir: Path; interfaces_dir: Path

  class Layouts(Protocol):
      def at(self, root: Path) -> AppLayout: ...
      def find(self, start: Path) -> AppLayout | None: ...
      def user_config_dir(self) -> Path: ...
      def user_data_dir(self) -> Path: ...
      def machine_local_ignores(self) -> list[str]: ...

  class Files(Protocol):
      def read_text(self, path: Path) -> str | None: ...
      def write_atomic(self, path: Path, text: str) -> None: ...
      def read_json(self, path: Path) -> object | None: ...
      def write_json(self, path: Path, data: object) -> None: ...
      def append_line(self, path: Path, line: str) -> None: ...

  @dataclass(frozen=True)
  class RunResult:
      argv: tuple[str, ...]; returncode: int; stdout: str; stderr: str; seconds: float

  class Spawned(Protocol):
      pid: int
      def alive(self) -> bool: ...
      def stop(self, grace: float = 5.0) -> None: ...

  class Runner(Protocol):
      def run(self, argv: Sequence[str], cwd: Path, env: Mapping[str, str] | None = None,
              timeout: float | None = None) -> RunResult: ...
      def spawn(self, argv: Sequence[str], cwd: Path, env: Mapping[str, str] | None = None,
                log: Path | None = None) -> Spawned: ...
      def which(self, tool: str) -> Path | None: ...

  class Clock(Protocol):
      def now(self) -> datetime: ...
  ```
- Behavior spec:
  - Layouts.at(root): every path per the **App folder** table (`run_dir` = `.bull/run`); `root`
    resolved to an absolute path.
  - Layouts.find(start): nearest folder at or above `start` holding `.bull/status.json` → its
    layout; none up to the filesystem root → None.
  - user_config_dir: `$XDG_CONFIG_HOME/bull` if set and absolute, else `~/.config/bull`;
    user_data_dir: `$XDG_DATA_HOME/bull`, else `~/.local/share/bull`.
  - machine_local_ignores → the six `.gitignore` lines in **App folder**, in that order.
  - Files.read_text: missing file → None. write_atomic: creates parent folders; writes a temp file
    in the same folder then `os.replace`; an interrupted write never leaves a partial target. The
    temp file is created exclusively under a random name; if the name is taken it retries with a
    new one (up to 100 times, then raises). A new file gets the process umask; an existing file
    keeps its mode.
  - Files.read_json: missing → None; invalid JSON → `FileFormatError` naming the path and line.
    write_json: `indent=2`, `sort_keys=True`, trailing newline, atomic.
  - append_line: appends `line + "\n"`, creating the file and folders.
  - Runner.run: merges `env` over the current environment; captures stdout/stderr as text;
    executable not found → `ToolMissing` naming it; a missing `cwd` is not `ToolMissing` (the
    original not-found error, naming the folder, is raised); timeout → returncode 124 and stderr
    ends with "timed out after <n>s" (the whole process group is killed, so a grandchild holding
    the output can't delay it); never uses a shell.
  - Runner.spawn: starts the process in its own process group, output to `log` (or discarded);
    `stop` sends SIGTERM to the group, waits `grace`, then SIGKILL; `alive` false after stop.
    `stop` is idempotent: on a process that already exited, or a second call, it signals nothing
    (its pid may have been reused). Executable not found, or missing `cwd` → as Runner.run.
  - Runner.which: `shutil.which` → Path or None.
  - Clock.now: timezone-aware UTC.
- Anticipated operations (not built yet): Windows path and process-group handling.
- Reference tests: none (helpers only).
- Contract: see `docs/api/foundation.md` (generated; do not edit by hand)

### gitrepo
- Purpose: every git operation bull needs, through the runner.
- Depends on: foundation
- Files: Contracts/__init__.py, mocks/__init__.py, git.py
- Protocol (draft; lives in `Contracts/`):
  ```python
  class GitError(BullError): ...

  class Git(Protocol):
      def is_repo(self, path: Path) -> bool: ...
      def toplevel(self, path: Path) -> Path | None: ...
      def init(self, path: Path, branch: str) -> None: ...
      def current_branch(self, root: Path) -> str | None: ...
      def head(self, root: Path, ref: str = "HEAD") -> str | None: ...
      def is_clean(self, root: Path) -> bool: ...
      def branch_exists(self, root: Path, name: str) -> bool: ...
      def create_branch(self, root: Path, name: str, start: str, switch: bool = True) -> None: ...
      def switch(self, root: Path, name: str) -> None: ...
      def commit_all(self, root: Path, message: str) -> str | None: ...
      def tag(self, root: Path, name: str, ref: str = "HEAD") -> None: ...
      def tags(self, root: Path, pattern: str = "*") -> list[str]: ...
      def changed_paths(self, root: Path, a: str, b: str) -> list[str]: ...
      def show_file(self, root: Path, ref: str, path: str) -> str | None: ...
      def parents(self, root: Path, ref: str) -> list[str]: ...
      def submodules(self, root: Path) -> list[str]: ...
      def active_hooks(self, root: Path) -> list[str]: ...
  ```
- Behavior spec:
  - head: full sha; unknown ref → None. current_branch: detached HEAD → None.
  - is_clean: false with staged, unstaged or untracked (not ignored) changes; ignored files don't
    count.
  - commit_all: stages everything (`git add -A`) and commits; nothing to commit → None.
  - tag on an existing tag name → `GitError` naming it. tags(pattern) sorted.
  - changed_paths(a, b): paths that differ between two commits (`--name-only`), sorted.
  - show_file: content of `path` at `ref`; missing → None.
  - parents(ref): parent shas in order (two for a merge commit).
  - active_hooks: names of executable files in the repo's hooks folder not ending `.sample`.
  - Any failing git command → `GitError` with git's stderr (first lines) and the command.
- Reference tests: none.
- Contract: see `docs/api/gitrepo.md` (generated; do not edit by hand)

### events
- Purpose: the machine-local, append-only event log (`.bull/events.jsonl`).
- Depends on: foundation
- Files: Contracts/__init__.py, mocks/__init__.py, event_log.py
- Protocol (draft; lives in `Contracts/`):
  ```python
  EventValue = str | int | float | bool | None

  class EventKind(Enum):
      STATUS = "status"; GATE_STEP = "gate_step"; AGENT_START = "agent_start"
      AGENT_END = "agent_end"; HOOK_BLOCK = "hook_block"; PAUSE = "pause"; RESUME = "resume"
      DECISION = "decision"

  @dataclass(frozen=True)
  class Event:
      time: datetime; kind: EventKind; data: Mapping[str, EventValue]

  class EventLog(Protocol):
      def append(self, kind: EventKind, **data: EventValue) -> None: ...
      def read(self) -> list[Event]: ...
  ```
- Behavior spec:
  - append: one JSON line `{"time", "kind", ...data}`; `time` from the clock.
  - append when the file can't be written: one warning on stderr per process, never raises.
  - read: events in file order; blank or unparseable lines skipped (not JSON, not an object, missing
    or invalid `time`/`kind`, or a data value that isn't str/int/float/bool/null); missing file → `[]`.
- Anticipated operations (not built yet): time report queries.
- Reference tests: none.
- Contract: see `docs/api/events.md` (generated; do not edit by hand)

### settings
- Purpose: layered, validated TOML settings with an extensible schema; `bull config show/set`.
- Depends on: foundation
- Files: Contracts/__init__.py, mocks/__init__.py | schema.py, toml_edit.py | loader.py, settings.py, cli.py
- Protocol (draft; lives in `Contracts/`):
  ```python
  SettingValue = int | bool | str | tuple[str, ...]

  class SettingType(Enum): INT = "int"; BOOL = "bool"; STR = "str"; CHOICE = "choice"; STR_LIST = "list"
  class Layer(Enum):
      BULL = "bull default"; STACK = "stack"; USER = "user"; APP = "app"; PART = "part"

  @dataclass(frozen=True)
  class Setting:
      key: str; type: SettingType; default: SettingValue | None; description: str
      choices: tuple[str, ...] = (); minimum: int | None = None; maximum: int | None = None
      layers: frozenset[Layer] = frozenset(Layer)

  @dataclass(frozen=True)
  class Resolved:
      key: str; value: SettingValue; layer: Layer; source: Path | None

  @dataclass(frozen=True)
  class ConfigProblem:
      file: Path; line: int; key: str; message: str

  class ConfigError(BullError):
      problems: list[ConfigProblem]

  @dataclass(frozen=True)
  class StackLayer:
      """A stack's own settings (schema) and its defaults for any key."""
      schema: tuple[Setting, ...]; values: Mapping[str, SettingValue]

  class Settings(Protocol):
      def schema(self) -> list[Setting]: ...
      def get(self, key: str, part: str | None = None) -> SettingValue: ...
      def show(self, part: str | None = None) -> list[Resolved]: ...
      def set(self, key: str, raw: str, layer: Layer = Layer.APP, part: str | None = None) -> Resolved: ...

  class SettingsLoader(Protocol):
      def load(self, app: AppLayout | None,
               stack_layer: Callable[[str], StackLayer]) -> Settings: ...
  ```
- Behavior spec:
  - schema: bull's keys per the **config.toml** table, plus each loaded stack's `[settings]`.
  - load: reads user, app and part files; the stack named by `stack` in the app file (one-part) or
    each part file supplies the stack layer through `stack_layer`; any problem in any file → one
    `ConfigError` listing every problem (file, line, key, message).
  - Unknown key in a file → problem "unknown setting `<key>`" with its line (line found by scanning
    the file for the key's assignment or its table; 0 if not found).
  - A value of the wrong type or out of range → problem naming the expected type, range or choices.
  - A key set in a layer it isn't allowed in (e.g. `stack` in the user file) → problem.
  - Missing `format` in an app or part file → problem; `format` handled by `formats`, not a setting.
  - get(key, part): the last layer that sets it wins; part layer only when `part` given (one-part
    app: the implicit part `app` reads the app file); unknown key → `BullError`.
  - show(part): every schema key with its value and the layer it came from, sorted by key.
  - set(key, raw, layer): parses `raw` by type (`int`, `true/false`, list as comma-separated), validates
    (`max_attempts many` → "max_attempts must be an integer ≥ 1"), writes the file for that layer
    (user / app / `parts/<part>.toml`), creating it with `format = 1` if missing. The edit keeps
    other lines and comments: replaces the key's existing line, else appends `key = value` as a
    dotted key; TOML strings and lists quoted correctly.
  - cli: `config show [--part p] [--json]` prints `key = value (layer)` lines; `config set <key>
    <value> [--user | --part p]` prints the resolved line.
- Anticipated operations (not built yet): settings page; per-part overrides of user keys.
- Reference tests: v1-tests/test_config.py::test_layers_pipeline_stack_app; v1-tests/test_parts.py::test_gates_read_the_part_file
- Contract: see `docs/api/settings.md` (generated; do not edit by hand)

### formats
- Purpose: `format` versions of the app's files and `bull migrate`.
- Depends on: foundation, gitrepo
- Files: Contracts/__init__.py, mocks/__init__.py, formats.py, cli.py
- Protocol (draft; lives in `Contracts/`):
  ```python
  class FormatTooOld(BullError): ...
  class FormatTooNew(BullError): ...

  @dataclass(frozen=True)
  class FileFormat:
      path: Path; found: int | None; current: int

  class Migration(Protocol):
      source: int  # migrates files from `source` to `source + 1`
      def apply(self, app: AppLayout) -> list[Path]: ...

  class Formats(Protocol):
      def current(self) -> int: ...
      def inspect(self, app: AppLayout) -> list[FileFormat]: ...
      def check(self, app: AppLayout) -> None: ...
      def migrate(self, app: AppLayout) -> list[Path]: ...
  ```
- Behavior spec:
  - current(): 1 in v2.0.
  - inspect: `format` of `status.json`, `backlog.json`, `config.toml`, each `parts/*.toml`
    (missing files skipped; a file without `format` → found None).
  - check: any file newer → `FormatTooNew` "this app's files are format N; this bull reads format
    C: upgrade bull" (fix: `uv tool upgrade <package>`); else any older or None →
    `FormatTooOld` "this app's files are format N; run `bull migrate`".
  - migrate: newer → `FormatTooNew`; all current → returns `[]` and prints "already format C";
    otherwise applies the registered migrations in order from the oldest found format, each
    returning the files it changed, then commits `chore: migrate bull files to format C` and
    returns the paths. A missing migration step → `BullError` naming it. Migrations are
    constructor-injected (empty registry in v2.0).
- Reference tests: none.
- Contract: see `docs/api/formats.md` (generated; do not edit by hand)

### memo
- Purpose: parse the memo (`docs/outline.md`), report its problems, and hold the memo and backlog
  templates.
- Depends on: foundation
- Files: Contracts/__init__.py, mocks/__init__.py | parser.py, problems.py | templates.py, templates/outline.md, templates/backlog.md, cli.py
- Protocol (draft; lives in `Contracts/`):
  ```python
  @dataclass(frozen=True)
  class ModuleEntry:
      name: str; line: int; part: str | None; depends: tuple[str, ...]
      units: tuple[tuple[str, ...], ...]
      legacy_files: tuple[str, ...]; legacy_tests: tuple[str, ...]; callers: tuple[str, ...]
      reference_tests: tuple[str, ...]
      changes: Mapping[str, tuple[str, ...]]       # slug → files
      contract_changes: Mapping[str, str]           # slug → description

  @dataclass(frozen=True)
  class BuildEntry:
      name: str; depends: tuple[str, ...]; line: int

  @dataclass(frozen=True)
  class Journey:
      number: int; title: str; part: str | None

  @dataclass(frozen=True)
  class SideRef:
      part: str; module: str

  @dataclass(frozen=True)
  class InterfaceEntry:
      name: str; file: str; format: str; provider: SideRef; consumers: tuple[SideRef, ...]
      contract_changes: Mapping[str, str]

  @dataclass(frozen=True)
  class LegacySection:
      app_shell: tuple[str, ...]; app_shell_tests: tuple[str, ...]
      legacy_folders: tuple[str, ...]; renames: Mapping[str, str]

  @dataclass(frozen=True)
  class Memo:
      build_order: tuple[BuildEntry, ...]; modules: tuple[ModuleEntry, ...]
      journeys: tuple[Journey, ...]; interfaces: tuple[InterfaceEntry, ...]
      parts: tuple[str, ...]; unmapped_reference_tests: tuple[str, ...]
      legacy: LegacySection | None
      parse_problems: tuple[MemoProblem, ...] = ()   # found while parsing (e.g. duplicate sections)

  @dataclass(frozen=True)
  class MemoProblem:
      line: int; message: str

  class MemoReader(Protocol):
      def parse(self, text: str) -> Memo: ...
      def section_items(self, text: str, heading: str) -> list[str]: ...
      def problems(self, memo: Memo, known_parts: Sequence[str], max_files: int) -> list[MemoProblem]: ...

  class Templates(Protocol):
      def names(self) -> list[str]: ...
      def text(self, name: str) -> str: ...
  ```
- Behavior spec:
  - parse `## Build order`: lines `<n>. <Name> (depends on: none | A, B)`.
  - parse `## Modules`: each `### <Name>` block's `- Key: value` lines: `Part`, `Depends on`
    (`none` → empty), `Files` (units split on `|`, files on `,`, trimmed, empty entries dropped),
    `Legacy files`, `Legacy tests`, `Callers to repoint`, `Reference tests` (comma-separated;
    `none` → empty), `Changes (<slug>)`, `Contract changes (<slug>)`. Fenced code blocks inside a
    block are skipped. Lines keep their 1-based line numbers.
  - parse `## User journeys`: `<n>. **<Title>** — …` with an optional indented `- Part: <p>`.
  - parse `## Interfaces`: `### <Name>` blocks with `- File: <path> (<format>)`, `- Provider:
    <part> / <Module>`, `- Consumers: <part> / <Module>, …`, `- Contract changes (<slug>): …`.
  - parse `## Constraints`: `- Parts: a (stack), b (stack)` → parts; absent → `()`.
  - parse `## Unmapped reference tests` and `## Legacy code` (`App shell:`, `App shell tests:`,
    `Legacy folders:`, `Renames: A → LegacyA, …`; other lines, including slugged keys such as
    `Changes (<slug>)`, are ignored); a missing section → empty / None.
  - A `## <heading>` that appears twice: the first section wins; the second is recorded in
    `parse_problems` as "duplicate section `## <heading>`" on its line.
  - An interface side without `/` parses as an empty part; a `- File:` without `(<format>)` parses as
    an empty format.
  - section_items(text, heading): top-level `- ` items under `## <heading>` (heading matched ignoring case; text after `- `,
    continuation lines joined); missing heading → `[]`.
  - problems, each with its line: module in build order without a `###` block or the reverse;
    duplicate module names (case-insensitive); a dependency that is unknown, not earlier in the
    build order, or (module block's `Depends on`) different from the build order line; a module
    without `Files`; a unit with more than `max_files` files; with parts: a module or journey part
    not in `known_parts`, a module without `Part` when there are several parts, a dependency on a
    module of another part ("`web / Import` depends on `cli / Export` in another part; use an
    interface"); an interface side naming an unknown module or part, or written without `<part> / ` ("`<Module>`
    needs `<part> / <Module>`"); an interface `File` without `(<format>)`; `Changes (<slug>)` naming a
    file not in the module's `Files`; every entry of `memo.parse_problems`. Interface problems use line
    0 (InterfaceEntry carries no line).
  - Templates: names `outline`, `backlog`; text returns the file; unknown name → `BullError` listing
    names. The outline template documents every line format above (stack-neutral wording).
  - cli: `bull template <name>` prints the template.
- Reference tests: v1-tests/test_parts.py::test_memo_part_problems; v1-tests/test_cli_misc.py::test_sections_and_lists
- Contract: see `docs/api/memo.md` (generated; do not edit by hand)

### usage
- Purpose: record plan usage samples and decide OK / PAUSE / UNKNOWN.
- Depends on: foundation, settings
- Files: Contracts/__init__.py, mocks/__init__.py, usage.py
- Protocol (draft; lives in `Contracts/`):
  ```python
  class UsageVerdict(Enum): OK = "OK"; PAUSE = "PAUSE"; UNKNOWN = "UNKNOWN"

  @dataclass(frozen=True)
  class UsageSample:
      time: datetime; five_hour: float | None; weekly: float | None
      five_hour_resets: datetime | None; weekly_resets: datetime | None

  @dataclass(frozen=True)
  class UsageCheck:
      verdict: UsageVerdict; reason: str; resets_at: datetime | None

  class Usage(Protocol):
      def record(self, sample: UsageSample) -> None: ...
      def latest(self) -> UsageSample | None: ...
      def check(self) -> UsageCheck: ...
  ```
- Behavior spec:
  - record: writes `usage.json` (format 1) atomically.
  - latest: missing or unreadable file → None.
  - check: no sample, or both percentages None → UNKNOWN "no usage data yet". A window whose reset
    time has passed counts as 0%. 5-hour ≥ `usage.pause_5h` → PAUSE "5-hour usage 92% ≥ 85%",
    `resets_at` = its reset; else weekly ≥ `usage.pause_weekly` → PAUSE likewise; else OK with both
    percentages in `reason`.
- Reference tests: none.
- Contract: see `docs/api/usage.md` (generated; do not edit by hand)

### stacks
- Purpose: find, load and validate stacks (built-in and installed), load their readers, and the
  per-app stack commands (select, rules, setup, check, run, install).
- Depends on: foundation, settings
- Files: Contracts/__init__.py, mocks/__init__.py | manifest.py, loader.py, registry.py | select.py, docs.py, cli.py
- Protocol (draft; lives in `Contracts/`):
  ```python
  class StackKind(Enum): APP = "app"; SERVICE = "service"; TOOL = "tool"
  class Maturity(Enum): EXPERIMENTAL = "experimental"; VERIFIED = "verified"; TEST = "test"
  class IssueLevel(Enum): BLOCK = "block"; FIX = "fix"; NOTE = "note"
  class Role(Enum): PROVIDER = "provider"; CONSUMER = "consumer"
  class StackError(BullError): ...

  @dataclass(frozen=True)
  class Requirement:
      tool: str; hint: str

  @dataclass(frozen=True)
  class GateCommands:
      preflight: tuple[str, ...]; setup: tuple[str, ...]; build_test: tuple[str, ...]
      build_test_fast: tuple[str, ...]; lint: tuple[str, ...]; rerun_failed: tuple[str, ...]
      journeys: tuple[str, ...] | None

  @dataclass(frozen=True)
  class RunCommands:
      start: tuple[str, ...]; ready: tuple[str, ...]; stop: tuple[str, ...]; ready_timeout: float

  @dataclass(frozen=True)
  class StackManifest:
      name: str; title: str; description: str; language: str; kind: StackKind
      maturity: Maturity; source_glob: str; test_glob: tuple[str, ...]; comment: str
      scaffold: tuple[str, ...]; gitignore: tuple[str, ...]; agents: tuple[str, ...]
      requires: tuple[Requirement, ...]; settings: StackLayer; gates: GateCommands
      run: RunCommands | None; interface_formats: tuple[str, ...]
      commands: Mapping[str, tuple[str, ...]]

  @dataclass(frozen=True)
  class CheckItem:
      ok: bool; item: str; fix: str

  @dataclass(frozen=True)
  class TestRun:
      count: int; failed: tuple[str, ...]

  @dataclass(frozen=True)
  class CoverageData:
      uncovered: Mapping[Path, tuple[int, ...]]; no_data: tuple[Path, ...]

  @dataclass(frozen=True)
  class Issue:
      level: IssueLevel; item: str; fix: str

  @dataclass(frozen=True)
  class Detection:
      confidence: float; summary: str; settings: Mapping[str, str]; issues: tuple[Issue, ...]

  class StackReaders(Protocol):
      """Functions every stack's readers.py defines."""
      def contract_declarations(self, path: Path) -> list[str]: ...
      def test_results(self, results: Path) -> TestRun | None: ...
      def uncovered(self, part_root: Path, sources: Sequence[Path], results: Path) -> CoverageData: ...
      def check(self, part_root: Path, settings: Mapping[str, SettingValue], adopting: bool) -> list[CheckItem]: ...

  @dataclass(frozen=True)
  class OptionalReaders:
      detect: Callable[[Path], Detection] | None
      inventory: Callable[[Path, Mapping[str, SettingValue]], str] | None
      legacy_declarations: Callable[[Path], list[str]] | None
      interface_check: Callable[[Path, Mapping[str, SettingValue], Path, str, Role, str], list[CheckItem]] | None

  @dataclass(frozen=True)
  class Stack:
      manifest: StackManifest; home: Path; builtin: bool
      readers: StackReaders; optional: OptionalReaders

  class StackRegistry(Protocol):
      def all(self, include_test: bool = False) -> list[Stack]: ...
      def get(self, name: str) -> Stack: ...
      def load_path(self, path: Path) -> Stack: ...
      def install(self, path: Path) -> Stack: ...

  class StackOps(Protocol):
      def select(self, app: AppLayout, name: str) -> None: ...
      def rules(self, stack: Stack, agent: str) -> str: ...
      def setup_guide(self, stack: Stack, section: str | None = None) -> str: ...
      def check(self, app: AppLayout, part: str | None = None) -> list[CheckItem]: ...
      def run_command(self, app: AppLayout, command: str, part: str | None = None) -> int: ...
  ```
- Behavior spec:
  - manifest: parses `stack.toml` per **Data models**; missing required key, bad enum value, a
    `TODO` placeholder, `[run]` without `start/ready/stop`, `name` not matching the folder or not a
    valid name, `_template`, missing `source_dir`/`test_dir` settings, or `agents` missing a
    required agent (skeleton-builder, test-writer, code-writer, reviewer, coverage-analyst; plus
    journey-test-writer when `journeys` is set; surveyor when `detect` exists) → `StackError`
    listing every problem.
  - loader: imports the folder's `readers.py` as a package `bull_stack_<name>` so it can import
    siblings; missing a required function → `StackError` naming it; optional functions absent →
    None in `OptionalReaders`.
  - registry.all: built-in stacks (folders with `stack.toml` under the built-in roots given to the
    constructor) plus installed ones (`<user_data_dir>/stacks/<name>/`), sorted by name; `test`
    maturity only with `include_test`. get(unknown) → `StackError` listing known names.
  - install(path): loads and validates the folder; name of a built-in → refused; copies it to
    `<user_data_dir>/stacks/<name>/` (replacing an earlier install of the same name); returns it.
    (`stack install` in the CLI also runs `stack test --static` first; see stacktest.)
  - select(app, name): one-part app only (with parts → `StackError` "use `bull part add`"); writes
    `stack` and the stack's `source_dir`/`test_dir` defaults into `config.toml`, merges the stack's
    `gitignore` lines into `.gitignore` (no duplicates), creates its `scaffold` folders; a
    `config.toml` it cannot edit safely (invalid TOML, or a key set in a form a line edit can't
    change) → `StackError` and nothing written.
  - rules(stack, agent): `## common` plus `## <agent>` from `rules.md` (heading match
    case-insensitive; no `## common` → the agent's section alone; `common` → that section once); `outline` → `## outline` only; agent not in the file → `StackError`.
  - setup_guide: whole `setup.md`, or one `## <section>`.
  - check(app, part): the stack's `check` for that part's folder and settings, `adopting` true while
    an adoption is active (read from `status.json`), plus bull's own items: each `requires` tool on
    PATH, source and test folders exist.
  - run_command: runs a `[commands]` entry with placeholders and environment as for gate steps;
    unknown → `StackError` listing the commands.
  - cli: `bull stacks [--all] [--json]` lists name, kind, maturity, title (and "installed"); `stack
    select|rules|setup|check|run|install` as above; `check` exits 1 if any item fails, printing
    `✗ item — fix` lines; `check` without `--part` in an app with part files checks every part,
    each under a `part <name> (<stack>)` heading, and exits 1 if any part has a failing item; any
    `--part` naming a part the app doesn't have → `StackError` naming the known parts.
- Anticipated operations (not built yet): installing from a package name; `stack uninstall`.
- Reference tests: v1-tests/test_stack_new.py::test_template_is_not_a_stack; v1-tests/test_parts.py::test_stack_commands_take_part
- Contract: see `docs/api/stacks.md` (generated; do not edit by hand)

### parts
- Purpose: an app's parts (folder + stack each), the implicit one-part case, and part checks.
- Depends on: foundation, settings, stacks
- Files: Contracts/__init__.py, mocks/__init__.py | parts.py, cli.py
- Protocol (draft; lives in `Contracts/`):
  ```python
  @dataclass(frozen=True)
  class Part:
      name: str; stack: str; dir: str; root: Path; source_dir: Path; test_dir: Path

  class Parts(Protocol):
      def all(self, app: AppLayout) -> list[Part]: ...
      def get(self, app: AppLayout, name: str | None = None) -> Part: ...
      def add(self, app: AppLayout, name: str, stack: str, dir: str | None = None) -> Part: ...
      def check(self, app: AppLayout) -> list[str]: ...
      def module_src(self, part: Part, module: str) -> Path: ...
      def module_tests(self, part: Part, module: str) -> Path: ...
      def is_test_path(self, app: AppLayout, path: Path) -> bool: ...
  ```
- Behavior spec:
  - all: one file per part in `.bull/parts/`, sorted; none and a `stack` in `config.toml` → one
    implicit part `app`, dir `.`; neither → `[]`.
  - get(None): the only part; several → `BullError` "say which part: a, b".
  - add: name must match `^[a-z][a-z0-9_]*$` and be new; stack must exist; `dir` defaults to the
    name, must be relative, inside the app, and not overlap another part (a root part `.` is
    allowed when its source and test folders don't contain the other part's folder); on an app
    with the implicit part, first moves `stack` and the stack keys from `config.toml` into
    `parts/app.toml`; writes `parts/<name>.toml` (`format`, `stack`, `dir`, stack defaults),
    merges the stack's gitignore lines prefixed with the folder (comments and blank lines kept
    as they are), creates its scaffold folders; `dir` may not be or lie inside bull's own app
    folders (`.bull`, `.git`, `docs`, `interfaces`). A one-part app never gets a `.bull/parts/`
    folder until `part add`.
  - check: overlapping folders, unknown stacks, missing folders → one message each.
  - module_src: `<root>/<source_dir>/Modules/<module>`; module_tests: `<root>/<test_dir>/<module>`.
  - is_test_path: inside any part's test folder, or matching any part's stack `test_glob`.
  - cli: `part add|list [--json]|check` (check prints each problem and exits 1, or prints `no problems`).
- Reference tests: v1-tests/test_parts.py::test_implicit_part, test_add_moves_the_implicit_part, test_existing_modules_still_resolve_after_the_move, test_rejects_bad_names_and_folders, test_check, test_stack_select_refused_once_parts_exist, test_anchored_patterns_move_under_the_part
- Contract: see `docs/api/parts.md` (generated; do not edit by hand)

### status
- Purpose: the pipeline state in `.bull/status.json`: stages and checkpoints (for the app, the
  active feature or the adoption), modules and units, attempts, pause, approval waits, the
  progress gauge, branch and tag names, and the next step.
- Depends on: foundation, gitrepo, events, settings, memo, parts
- Files: Contracts/__init__.py, mocks/__init__.py | model.py, store.py, refs.py | transitions.py, modules.py, next_step.py | summary.py, cli.py
- Protocol (draft; lives in `Contracts/`):
  ```python
  class Mode(Enum): APP = "app"; FEATURE = "feature"; ADOPT = "adopt"
  class UnitState(Enum): PENDING = "pending"; TESTS = "tests"; CODE = "code"; DONE = "done"; BLOCKED = "blocked"
  class ModuleState(Enum): PENDING = "pending"; IN_PROGRESS = "in_progress"; DONE = "done"; BLOCKED = "blocked"
  class UnitKind(Enum): CODE = "code"; SWITCH_OVER = "switch-over"
  class StatusError(BullError): ...

  @dataclass(frozen=True)
  class Unit:
      number: int; files: tuple[str, ...]; kind: UnitKind; state: UnitState; attempts: int

  @dataclass(frozen=True)
  class ScanRecord:
      time: datetime; covered: int; missed: int; contradicts: int; not_in_spec: int

  @dataclass(frozen=True)
  class ModuleStatus:
      name: str; part: str; depends: tuple[str, ...]; state: ModuleState
      units: tuple[Unit, ...]; reference_tests: bool; scan: ScanRecord | None

  @dataclass(frozen=True)
  class Track:
      stage: int; checkpoints: tuple[str, ...]

  @dataclass(frozen=True)
  class Pause:
      reason: str; since: datetime; unit: str | None

  @dataclass(frozen=True)
  class Waiting:
      module: str; what: str; since: datetime

  @dataclass(frozen=True)
  class Approval:
      module: str; note: str; time: datetime

  @dataclass(frozen=True)
  class PlanItem:
      name: str; done: bool

  @dataclass(frozen=True)
  class Plan:
      label: str; items: tuple[PlanItem, ...]

  @dataclass(frozen=True)
  class ActiveFeature:
      slug: str; track: Track; applied_contracts: tuple[str, ...]

  @dataclass(frozen=True)
  class Status:
      format: int; app: Track; modules: tuple[ModuleStatus, ...]; pause: Pause | None
      waiting: Waiting | None; approvals: tuple[Approval, ...]; plan: Plan | None
      feature: ActiveFeature | None; adoption: Track | None

  @dataclass(frozen=True)
  class NextStep:
      text: str; mode: Mode

  class StatusStore(Protocol):
      def load(self) -> Status: ...
      def create(self) -> Status: ...
      def mode(self) -> Mode: ...
      def set_stage(self, stage: int) -> Status: ...
      def checkpoint(self, name: str) -> Status: ...
      def init_modules(self, memo: Memo, replace: bool = False) -> Status: ...
      def set_module(self, name: str, state: ModuleState) -> Status: ...
      def set_unit(self, name: str, number: int, state: UnitState) -> Status: ...
      def attempt(self, name: str, number: int) -> Unit: ...
      def unblock(self, name: str, number: int) -> Status: ...
      def pause(self, reason: str) -> Status: ...
      def resume(self) -> Status: ...
      def wait(self, module: str, what: str) -> Status: ...
      def approve(self, module: str, note: str) -> Status: ...
      def take_approval(self, module: str) -> Approval | None: ...
      def record_scan(self, module: str, covered: int, missed: int, contradicts: int, not_in_spec: int) -> Status: ...
      def set_plan(self, label: str, items: Sequence[str]) -> Status: ...
      def tick(self, item: str) -> Status: ...
      def clear_plan(self) -> Status: ...
      # used by features and adoption:
      def start_feature(self, slug: str) -> Status: ...
      def end_feature(self) -> Status: ...
      def mark_contract_applied(self, module: str) -> Status: ...
      def reopen(self, module: str, files: Sequence[str]) -> Status: ...
      def add_modules(self, entries: Sequence[ModuleEntry]) -> Status: ...
      def start_adoption(self) -> Status: ...
      def finish_adoption(self) -> Status: ...
      def abandon_adoption(self) -> Status: ...

  class Refs(Protocol):
      def trunk(self) -> str: ...
      def base(self) -> str: ...
      def module_branch(self, module: str) -> str: ...
      def tag(self, label: str) -> str: ...
      def module_for_branch(self, branch: str) -> str | None: ...

  class Progress(Protocol):
      def next_step(self) -> NextStep: ...
      def summary(self) -> str: ...
      def as_json(self) -> dict[str, object]: ...
      def tags(self) -> list[str]: ...
  ```
- Behavior spec:
  - Every change: validate, write `status.json` atomically, append a `status` event (`what`,
    module, unit, state…). A refused change raises `StatusError` with the reason and writes nothing.
  - create: format 1, kind app, stage 0, no checkpoints, no modules; refuses if the file exists.
  - load: missing file → `StatusError` "not a bull app (no .bull/status.json)"; `kind` "stack" →
    `StatusError` "this is a stack repo".
  - mode: adoption active → ADOPT; feature active → FEATURE; else APP. Stage and checkpoint changes
    apply to that mode's track.
  - set_stage(n): 0–6; moving forward needs the checkpoints that close earlier stages — stage 3
    needs `outline-approved` and `setup`, 4 needs `skeleton`, 5 needs `ui-approved` (adopt:
    3 needs `outline-approved` and `setup`, 4 needs `baseline`, 5 needs `scaffold`), 6 needs every
    module done; moving back is allowed.
  - checkpoint(name): name must belong to the mode's list (app: `outline-approved`, `setup`,
    `skeleton`, `ui-approved`, `app-accepted`; feature: the same plus `accepted`; adopt:
    `outline-approved`, `setup`, `baseline`, `scaffold`, `adopted`); `app-accepted`/`accepted`/
    `adopted` need stage 6; recording twice is a no-op.
  - init_modules(memo): memo problems (with the app's parts and `max_files_per_unit`) → refused
    listing every problem with its line; modules in build order with part (the only part when the
    memo has none), depends, one unit per `Files` group (state pending, attempts 1),
    `reference_tests` true when the memo line is non-empty; while adopting, a module with
    `Legacy files` gets a final switch-over unit (no files); existing modules past pending →
    refused unless `replace`. With `replace`, a module still in the memo keeps each unit whose
    number, kind and files are unchanged (state and attempts kept); other units start pending with
    attempts 1; the module keeps its state (and scan record) when every unit was kept, else becomes `in_progress` if
    any unit is past pending, else `pending`. Modules no longer in the memo are dropped.
  - set_module(M, in_progress): every dependency must be done, else refused naming them; unknown
    module → refused with "did you mean `Counter`?" for a case-insensitive match, else the list of
    modules. done: every unit done.
  - set_unit: pending → tests → code → done in order (tests may be set again from code for a
    retry: `code → tests` allowed); blocked unit → refused until unblocked.
  - attempt(M, n): attempts < `max_attempts` → attempts + 1, back to `tests` state's successor
    (`code` work redone: state `tests`); attempts = `max_attempts` → unit `blocked`, refused with
    "unit n blocked after 3 attempts; ask the human".
  - unblock: state back to `tests`, attempts 1.
  - pause(reason): records reason, time and the unit in progress ("Counter unit 2") and a `pause`
    event; resume clears it (`resume` event); resume when not paused → no-op.
  - wait(M, what) / approve(M, note): approve clears a matching wait, appends an approval and a
    `decision` event; take_approval returns and removes the oldest approval for the module.
  - record_scan: only for a module with `reference_tests`; counts ≥ 0.
  - set_plan / tick / clear_plan: tick of an unknown item → refused.
  - start_feature(slug): refused unless `app-accepted`, no adoption, no active feature; feature
    track stage 1. end_feature clears it. reopen(M, files): units holding those files → pending,
    attempts 1; module → pending. add_modules: appends new modules from memo entries.
  - start_adoption: refused if any module exists or the app track is past stage 0; adoption track
    stage 1. finish_adoption: needs adoption stage 6; adds `adopted` to the adoption track, records
    `app-accepted` on the app track with stage 6, and clears the adoption.
  - Refs: trunk = `base_branch`; prefix: none (APP), `feature/<slug>/` (FEATURE), `adopt/` (ADOPT);
    base = trunk, `feature/<slug>/main`, `adopt/main`; module_branch = `<prefix>module/<M>`;
    tag(label) = `<prefix><label>` except `adopted` (always unprefixed); module_for_branch parses
    a module branch of the current mode.
  - next_step, by priority: paused → "paused (<reason>): run /bull:resume"; waiting → "waiting for
    the human to approve the <M> contract change"; a blocked unit → "<M> unit n is blocked: ask the
    human"; then by stage: 0–1 → `/bull:discuss`; 2 → `/bull:outline` or, after
    `outline-approved`, `/bull:setup`; 3 → `/bull:skeleton`; 4 → `/bull:prototype`; 5 → the module
    in progress: first unfinished unit (pending → "unit n: test-writer", tests → "unit n:
    code-writer, then gates --fast", code → "unit n: reviewer"; switch-over units say
    "switch-over"); all units done → "reference-test scan for <M>" when `reference_tests` and no
    scan, else "coverage triage, full gates, merge <branch> into <base>"; no module in progress →
    "start <M> on <branch>" for the first pending module whose dependencies are done; all done →
    "`bull gates --all`, then /bull:verify"; 6 → `/bull:verify`, or after `app-accepted`
    `/bull:feature`. FEATURE and ADOPT prefix "feature <slug>:" / "adoption:" and use their
    commands (`/bull:feature`, `/bull:adopt`). When the current git branch is neither the base nor
    the module branch in progress, the text starts "switch to <branch>, then".
  - summary: stage (and mode), checkpoints, units done/total, each module's state and units,
    pause/wait, plan, next step.
  - as_json: the status file's content plus `mode`, `next`, `units_done`, `units_total`.
  - tags: git tags matching the pipeline's names (checkpoints, `module/*`, `feature/*`, `adopt/*`,
    `adopted`), sorted.
  - cli: every `bull status …` command in **Commands**; refusals exit 1 with the reason; `usage-check`
    prints `OK|PAUSE|UNKNOWN: <reason>` (exit 0 for all three; `--json` gives the fields).
- Construction (internal; not contracts):
  - model.py: `status_from_json(data: object) -> Status` (malformed → `FileFormatError` naming
    the field) and `status_to_json(status: Status) -> dict[str, object]`; times are ISO 8601 UTC
    with `Z`.
  - store.py: `LiveStatusStore(app: AppLayout, files: Files, events: EventLog, clock: Clock,
    settings: Settings, parts: Parts, memo_reader: MemoReader)`. It owns create, load, mode and the
    write path (load → apply → validate → atomic write → one `status` event, whose `what` is the
    method name). Every other change method delegates to a pure function in transitions.py or
    modules.py with the same name and arguments, taking the current `Status` first and keyword-only
    context (`now: datetime`, `max_attempts: int`, `known_parts`, `max_files`, `problems`) as it
    needs, returning the new `Status` (`attempt` → `tuple[Status, Unit]`, `take_approval` →
    `tuple[Status, Approval | None]`) and raising `StatusError` on refusal. modules.py holds
    init_modules, set_module, reopen, add_modules; transitions.py holds the rest. Unit 2 may add
    those functions as `NotImplementedError` stubs; unit 3 implements and tests them (directly and
    through the store).
  - attempt at the limit: `transitions.attempt` returns the new `Status` with the unit `blocked`;
    the store writes it and logs the `status` event, then raises `StatusError` "unit n blocked
    after <max_attempts> attempts; ask the human" (the one refusal that saves its change).
  - Unit 3 also finishes the store side (it may edit store.py and model.py): attempt at the limit
    as above; a no-op change (checkpoint recorded twice, resume when not paused, take_approval with
    none) writes nothing and logs nothing; `pause` logs `status` + `pause`, `resume` `status` +
    `resume`, `approve` `status` + `decision` (tests pin the exact event set); init_modules and
    add_modules pass `known_parts` and `problems` through; `status_from_json` refuses stage
    outside 0–6, attempts or unit number < 1 and negative scan counts, naming the field.
  - next_step.py: pure `next_step(status: Status, mode: Mode, refs: Refs, branch: str | None) ->
    NextStep` (`branch` = current git branch, None when unknown). summary.py (unit 4) holds
    `LiveProgress(store: StatusStore, refs: Refs, git: Git)`, which calls it.
  - summary.py: `LiveProgress(app: AppLayout, store: StatusStore, refs: Refs, git: Git)`;
    each call loads the status once and derives the mode from it;
    next_step uses `git.current_branch(app.root)`; tags uses `git.tags(app.root, …)`.
  - cli.py (decisions-log convention): `register(commands, store: Callable[[], StatusStore], refs:
    Callable[[], Refs], progress: Callable[[], Progress], usage: Callable[[], Usage], memo:
    Callable[[], Memo]) -> None` (`memo` = the parsed `docs/outline.md`, built by `cli.wiring`).
    Routing `status` to stackflow in a stack repo is `cli.wiring`'s job; here a stack repo is
    refused through `store.load()`.
  - refs.py: `LiveRefs(settings: Settings, store: StatusStore)`; mode and feature slug come from
    one `store.load()` (mode derived from that status, as `mode` does), the trunk from `settings.get("base_branch", None)`.
  - Guards (coverage triage, approved 2026-11-08): a naive time (e.g. from the clock) is treated as UTC, so the change saves; a module with
    no part when the app has no parts → refused ("add a part with `bull part add`"); reopen with no
    unit holding any of the files → refused (files no unit holds are otherwise ignored);
    add_modules with an existing name → refused; build-order names match module blocks case-insensitively (as memo problems do; the block's name is used); a build-order entry with no module block → refused; no module in progress, none can start, not all
    done → "no module can start (not done: <M>, …): ask the human"; `base_branch` empty or not a
    string → refused; `max_attempts` / `max_files_per_unit` not an integer → refused; end_feature
    and mark_contract_applied with no active feature → refused; mark_contract_applied twice →
    no-op; start_adoption while an adoption or a feature is active → refused; abandon_adoption
    clears the adoption, leaves the app track as it was, and is refused when none is active.
- Anticipated operations (not built yet): time totals from the event log.
- Reference tests: v1-tests/test_adopt_status.py (all cases except test_start_needs_a_clean_tree_on_the_trunk, test_finish_waits_for_verify, test_abandon_keeps_the_trunk_and_carries_the_backlog, test_app_shell_tests_are_not_old_tests, which map to adoption); v1-tests/test_parts.py::test_modules_get_their_part; v1-tests/test_gate_speed.py::test_wrong_case_suggests_the_module, test_unknown_module_lists_the_modules
- Contract: see `docs/api/status.md` (generated; do not edit by hand)

### features
- Purpose: the feature backlog (`.bull/backlog.json`), idea import, briefs, and the feature cycle
  commands.
- Depends on: foundation, gitrepo, memo, status
- Files: Contracts/__init__.py, mocks/__init__.py | backlog.py, ideas.py, briefs.py | cycle.py, cli.py
- Protocol (draft; lives in `Contracts/`):
  ```python
  class ItemState(Enum):
      QUEUED = "queued"; ACTIVE = "active"; ACCEPTED = "accepted"; ABANDONED = "abandoned"; DROPPED = "dropped"

  @dataclass(frozen=True)
  class BacklogItem:
      slug: str; title: str; description: str; state: ItemState; added: datetime; brief: str

  @dataclass(frozen=True)
  class Idea:
      title: str; description: str

  @dataclass(frozen=True)
  class FeaturePlan:
      reopened: Mapping[str, tuple[int, ...]]; new_modules: tuple[str, ...]
      contract_changes: tuple[str, ...]; skeleton_needed: bool

  class Backlog(Protocol):
      def items(self) -> list[BacklogItem]: ...
      def add(self, idea: Idea, top: bool = False) -> BacklogItem: ...
      def import_ideas(self, ideas: Sequence[Idea]) -> list[BacklogItem]: ...
      def move(self, slug: str, position: int) -> None: ...
      def drop(self, slug: str) -> None: ...

  class IdeaReader(Protocol):
      def read(self, text: str, section: str | None = None) -> list[Idea]: ...
      def slug(self, title: str, taken: Collection[str]) -> str: ...

  class FeatureCycle(Protocol):
      def start(self, slug: str | None = None) -> BacklogItem: ...
      def plan(self) -> FeaturePlan: ...
      def accept(self) -> BacklogItem: ...
      def abandon(self) -> BacklogItem: ...
  ```
- Behavior spec:
  - IdeaReader.read: a file with `## <Title>` sections → one idea per section (body, trimmed, is the
    description); otherwise one idea per top-level `- <Title>: <description>` item (no colon → whole
    text is the title); with `section`, only the items under `## <section>` (heading matched
    case-insensitively); nothing found → `[]`. An indented continuation line under a list item is
    joined to its description with a newline; checkbox items: `- [x] …` (checked) is skipped,
    `- [ ] B` is read as `- B`.
  - slug: lowercase, runs of non-alphanumerics → `-`, trimmed, at most 40 characters cut at a `-`;
    taken → suffix `-2`, `-3`, …
  - add: new item `queued` at the end (or top), writes `docs/features/<slug>.md` from the brief
    template (`# <Title>`, `## Idea`, `## Discussion notes`, `## Agreed scope`).
  - import_ideas: skips ideas whose slug (or title, case-insensitive) is already in the backlog;
    returns the added items. CLI `--dry-run` lists them without writing.
  - move(slug, position): 1-based among queued items; drop: `queued` → `dropped` (brief kept).
  - start(slug): first queued when None; refused unless on a clean trunk, `app-accepted`, no
    adoption (message says it can start after the adoption finishes), no active feature, and no
    existing `feature/<slug>/main` branch (all checked before any write); add and import work
    during an adoption; marks the item active, `status.start_feature`, commits `chore: start feature
    <slug>`, creates and switches to `feature/<slug>/main`.
  - plan: on the feature branch; reads the memo and runs `status.init_modules(memo, replace=True)`:
    the memo's `Files` groups decide where a file new to an existing module goes (an existing `|`
    group → that unit; a new group, added at the end → a new unit); unchanged units keep their
    progress, changed or new units start pending, modules not yet in status are added in build
    order. Then modules with `Changes (<slug>)` → `status.reopen` with those files. `new_modules`
    are the memo modules that were not in status before; contract changes listed;
    `skeleton_needed` when there are new modules or contract changes. Memo problems → refused
    before any change (from init_modules).
  - accept: refused unless the feature track is at stage 6 with `accepted` recorded; then the item
    is marked accepted and `status.end_feature` runs. Only backlog and status change; the
    orchestrator edits the memo.
  - abandon: run on the trunk; item abandoned, `status.end_feature`; items present in the feature
    branch's `backlog.json` (read with `git show`) but missing on the trunk are added (queued).
  - cli: `bull feature …` per **Commands**; `list` shows position, slug, state, title in file
    order; position is the 1-based queued position (the number `move` takes), `-` for items not
    queued; `list --json` objects carry `position` (null when not queued), `slug`, `state`, `title`.
  - plan output: one `Reopened <Module>: unit <n>, …` line per reopened module, then `New modules:
    …` and `Contract changes: …` when non-empty, or `Nothing to reopen or add.` when all three are
    empty; last line `Skeleton needed: yes|no`.
  - Guards (coverage triage): a `backlog.json` that is not an object with `format` 1 and a list
    `items`, or an item missing a field, with a non-string field, an unknown state or a bad time →
    `FileFormatError` naming the file; `move`/`drop` of a slug that is not queued → refused ("No
    queued feature <slug>", hint `bull feature list`); `move` to a position outside 1…(queued
    count) → refused; `import` of a file that exists but can't be read → refused naming the path;
    `plan` with no memo file → refused ("write the memo first"); `accept`/`abandon` when the active
    feature's slug is not in the backlog → refused; `abandon` when the feature branch's
    `backlog.json` is invalid JSON → `FileFormatError` naming `<branch>:<path>`; `slug` of a title
    with no letters or digits → refused.
- Reference tests: v1-tests/test_cli_misc.py::test_sections_and_lists, test_slugs_are_unique; v1-tests/test_adopt_status.py::test_features_queue_during_adoption_but_start_only_after_it
- Contract: see `docs/api/features.md` (generated; do not edit by hand)

### coverage
- Purpose: turn a stack's coverage data into the triage report, honoring `coverage-exempt`
  markers.
- Depends on: foundation, stacks
- Files: Contracts/__init__.py, mocks/__init__.py, markers.py, triage.py
- Protocol (draft; lives in `Contracts/`):
  ```python
  @dataclass(frozen=True)
  class Exemption:
      path: Path; lines: tuple[int, ...] | None; reason: str  # None: whole file (no-data only)

  @dataclass(frozen=True)
  class MarkerScan:
      exemptions: tuple[Exemption, ...]; invalid: tuple[str, ...]

  @dataclass(frozen=True)
  class CoverageReport:
      module: str; uncovered: Mapping[Path, tuple[int, ...]]; no_data: tuple[Path, ...]
      exempted: tuple[Exemption, ...]; invalid_markers: tuple[str, ...]
      @property
      def clean(self) -> bool: ...

  class CoverageTriage(Protocol):
      def markers(self, path: Path, comment: str) -> MarkerScan: ...
      def sources(self, module_dir: Path, part_root: Path, source_glob: str, exclude: Sequence[str]) -> list[Path]: ...
      def report(self, module: str, sources: Sequence[Path], data: CoverageData, comment: str) -> CoverageReport: ...
      def render(self, report: CoverageReport) -> str: ...
  ```
- Behavior spec:
  - markers: `<comment> coverage-exempt: <reason>` at a line's end exempts that line;
    `coverage-exempt-begin: <reason>` … `coverage-exempt-end` exempts every line between them,
    inclusive; `coverage-exempt-file: <reason>` within the first 10 lines exempts the file from
    "no data" only. Missing reason, an unclosed begin, a stray end, or a begin inside an open
    block (`<path>:<line>: coverage-exempt-begin inside an open block`; the open block continues)
    → an invalid marker (`<path>:<line>: …`) that exempts nothing.
  - sources: files under `module_dir` matching `source_glob`, minus those matching any `exclude`
    glob (matched against the path relative to `part_root`, or the full path for a file outside
    `part_root`), sorted; directories whose names match `source_glob` are not sources.
  - report: for each source, uncovered lines minus exempted lines; a file without data is reported
    unless it has a file marker; a file marker never hides uncovered lines in a file that has data,
    and on a file that has data it is reported as an invalid marker (`<path>:<line>: unnecessary
    file marker`) so it gets removed;
    data for files outside `sources` ignored; `clean` = no uncovered lines, no reported no-data
    files, no invalid markers.
  - render: "coverage clean for <M>" or per file `path: lines 3, 7-9` (ranges collapsed), then
    "without coverage data: …" and invalid markers.
- Reference tests: v1-tests/test_gates_and_coverage.py::test_declaration_only_file_with_marker_passes, test_file_without_data_and_without_marker_fails, test_marker_does_not_hide_uncovered_code, test_line_and_block_markers
- Contract: see `docs/api/coverage.md` (generated; do not edit by hand)

### api
- Purpose: contract snapshots (`docs/api/<Module>.md`, `docs/api/interfaces/<Name>.md`), the `api`
  check, and the approval rule for writing a changed snapshot.
- Depends on: foundation, memo, stacks, parts, status
- Files: Contracts/__init__.py, mocks/__init__.py | snapshots.py, approval.py, cli.py
- Protocol (draft; lives in `Contracts/`):
  ```python
  class ApprovalNeeded(BullError): ...

  @dataclass(frozen=True)
  class Snapshot:
      name: str; files: Mapping[str, tuple[str, ...]]   # relative path → declarations

  @dataclass(frozen=True)
  class ApiCheck:
      name: str; ok: bool; stored: bool; diff: str

  class ApiSnapshots(Protocol):
      def current(self, app: AppLayout, module: str) -> Snapshot: ...
      def check(self, app: AppLayout, module: str) -> ApiCheck: ...
      def write(self, app: AppLayout, module: str, approved: str | None = None) -> Path | None: ...
      def check_interface(self, app: AppLayout, name: str) -> ApiCheck: ...
      def write_interface(self, app: AppLayout, name: str, approved: str | None = None) -> Path | None: ...
      def render(self, snapshot: Snapshot) -> str: ...
      def parse(self, text: str) -> Snapshot: ...
  ```
- Behavior spec:
  - current: every file under the module's `Contracts/` matching the part stack's `source_glob`
    (sorted), each read with the stack's `contract_declarations`; missing `Contracts/` →
    `BullError`.
  - render: `# <Name> contract`, a "generated by `bull api`; do not edit" comment, then per file
    `## <path>` and a fenced block of its declarations; parse is its inverse, and refuses damaged
    text with `BullError`: no `# <Name> contract` first line ("not a contract snapshot: missing the
    `# <Name> contract` heading"), a `## <path>` not followed by a fence ("contract snapshot: `##
    <path>` has no fenced block"), a block never closed ("contract snapshot: unclosed block for
    `<path>`").
  - check: no stored snapshot → not ok, `stored` false, diff "no snapshot: run `bull api <M>
    --write`"; else ok when equal, otherwise a unified diff (stored → current).
  - write: no stored snapshot or equal → writes (or no-op, returns None when equal). Changed → needs
    one of: `approved` note (logged as a `decision` event), an approval from `status.take_approval`,
    or — in FEATURE mode — the module has `Contract changes (<slug>)` in the memo and is not yet in
    `applied_contracts` (then `status.mark_contract_applied`); none → `ApprovalNeeded` "the <M>
    contract changed; the human must approve (bull status approve <M> "<note>")".
  - interfaces: same rules for the interface file named in the memo's `## Interfaces` (snapshot is
    the file's text in one fenced block; the memo entry's `Contract changes (<slug>)` pre-approves;
    the named file missing → `BullError` "interface <Name>: file <file> not found").
  - cli: `bull api <M>` prints the check (exit 1 when not ok); `--check` same quietly; `--write`
    per the rules.
- Construction (internal; not contracts):
  - snapshots.py: `LiveApiSnapshots(files: Files, parts: Parts, stacks: StackRegistry, memo:
    Callable[[], Memo], store: StatusStore)`. A module's `Contracts/` is
    `parts.module_src(parts.get(app, entry.part), M) / "Contracts"` (entry = the memo's module
    block; no block → `BullError` "unknown module <M>"); the stack is `stacks.get(part.stack)`, its
    `manifest.source_glob` and `readers.contract_declarations`. Snapshot paths are relative to the
    module folder (e.g. `Contracts/__init__.py`), POSIX. Stored files: `app.api_dir / "<M>.md"`
    and `app.api_dir / "interfaces" / "<Name>.md"` (interface name not in the memo's
    `## Interfaces` → `BullError` "unknown interface <Name>"; its file is `app.root / entry.file`;
    its snapshot has one entry keyed by `entry.file`). check compares the stored text with
    `render(current)`; the diff is `difflib.unified_diff` over lines with `fromfile="stored"`,
    `tofile="current"`. All reads and writes go through `files` (`read_text`, `write_atomic`).
  - approval.py: `authorize(name: str, approved: str | None, store: StatusStore,
    contract_changes: Mapping[str, str]) -> None`, called by write only when the snapshot changed,
    checked in order: an `approved` note → `store.approve(name, note)` (which logs the `decision`
    event) then `store.take_approval(name)`; else `store.take_approval(name)` returning an
    approval; else FEATURE mode (`store.mode()`), the active feature's slug in
    `contract_changes` and `name` not in its `applied_contracts` → `store.mark_contract_applied(name)`;
    else `ApprovalNeeded` with the spec's message (`<M>` = name).
  - cli.py (decisions-log convention): `register(commands, snapshots: Callable[[], ApiSnapshots],
    app: Callable[[], AppLayout]) -> None`. `bull api <M>` / `bull api --interface <Name>` (exactly
    one): ok → "api: <M> matches its snapshot", exit 0; not ok → "api: <M> differs from its
    snapshot" then the diff, exit 1. `--check`: nothing printed, same exit. `--write [--approved
    "<note>"]`: "wrote <path>" or "api: <M> unchanged", exit 0 (`ApprovalNeeded` propagates).
    `--approved` without `--write`, or `--check` with `--write` → `BullError`.
- Reference tests: none mapped (v1's api scanner tests were inside the stack scanners).
- Contract: see `docs/api/api.md` (generated; do not edit by hand)

### interfaces
- Purpose: interfaces between parts: memo entries, which modules provide or consume them, the
  per-side check through each side's stack, and which parts must run for a part's journeys.
- Depends on: foundation, settings, memo, stacks, parts, api
- Files: Contracts/__init__.py, mocks/__init__.py, interfaces.py
- Protocol (draft; lives in `Contracts/`):
  ```python
  @dataclass(frozen=True)
  class InterfaceResult:
      interface: str; part: str; module: str; role: Role; items: tuple[CheckItem, ...]
      @property
      def ok(self) -> bool: ...

  class Interfaces(Protocol):
      def for_module(self, memo: Memo, module: str) -> list[tuple[InterfaceEntry, Role]]: ...
      def problems(self, app: AppLayout, memo: Memo) -> list[str]: ...
      def check_module(self, app: AppLayout, memo: Memo, module: str) -> list[InterfaceResult]: ...
      def parts_to_run(self, memo: Memo, part: str) -> list[str]: ...
  ```
- Behavior spec:
  - for_module: each interface where the module is the provider or a consumer, with its role.
  - problems: interface file missing; its format not in the side's stack `interface_formats`; the
    side's stack has no `interface_check`.
  - check_module: for each of the module's interfaces, the side's stack `interface_check(part_root,
    settings, interface file, format, role, module)`; a module with none → `[]`.
  - parts_to_run(part): providers' parts of every interface any module of `part` consumes, whose
    stack has `[run]`, in build order, without duplicates and without `part` itself.
- Construction (internal; not contracts):
  - interfaces.py: `LiveInterfaces(parts: Parts, stacks: StackRegistry, settings: Settings)`
    (`settings` is the app's loaded settings). A side is a `SideRef`; its part is
    `parts.get(app, side.part)`, its stack `stacks.get(part.stack)` (in `parts_to_run`, which has
    no app: `stacks.get(settings.get("stack", side.part))`), its settings
    `{r.key: r.value for r in settings.show(side.part)}`. The interface file is
    `app.root / entry.file`. Modules match `SideRef.module` by exact name.
  - for_module: in memo order; provider role when the module is the provider, else consumer.
  - problems, one line each, in memo order, without duplicates: "interface <Name>: file <file>
    not found" (once per interface); then per side (provider, then consumers in order): "interface
    <Name>: format <format> is not supported by the <stack> stack (part <part>)" and "interface
    <Name>: the <stack> stack has no interface check (part <part>)".
  - check_module: one `InterfaceResult` per (interface, role) from for_module; `part` is the
    module's side's part; `items` are interface_check's return. A stack without `interface_check`
    → one item `CheckItem(False, "interface check for <format>", "the <stack> stack has no
    interface check")`, no exception. `InterfaceResult.ok`: every item ok (no items → True).
  - parts_to_run: interfaces with a consumer whose part is `part`; their providers' parts ordered
    by the provider module's position in `memo.build_order` (a provider not in the build order goes
    last, in memo order); stack `manifest.run is not None`. A part whose `stack` setting is not a
    string → `BullError` "part <part>: the stack setting is not a name" (fix "set the part's stack
    to a stack name").
- Reference tests: none (new in v2).
- Contract: see `docs/api/interfaces.md` (generated; do not edit by hand)

### adoption
- Purpose: adopting an existing one-part app: detection report, start / finish / abandon, and the
  legacy check.
- Depends on: foundation, gitrepo, settings, memo, stacks, parts, status, features
- Files: Contracts/__init__.py, mocks/__init__.py | detect.py, adopt.py, legacy.py, cli.py
- Protocol (draft; lives in `Contracts/`):
  ```python
  @dataclass(frozen=True)
  class DetectionReport:
      stack: str | None; detection: Detection | None; issues: tuple[Issue, ...]
      @property
      def blocked(self) -> bool: ...

  @dataclass(frozen=True)
  class LegacyLeft:
      files: tuple[str, ...]; declarations: tuple[str, ...]; tests: tuple[str, ...]; memo_files: tuple[str, ...]
      @property
      def empty(self) -> bool: ...

  class Adoption(Protocol):
      def detect(self, root: Path) -> DetectionReport: ...
      def apply(self, app: AppLayout, report: DetectionReport, stack: str | None = None) -> None: ...
      def start(self, app: AppLayout) -> None: ...
      def legacy(self, app: AppLayout) -> LegacyLeft: ...
      def finish(self, app: AppLayout) -> None: ...
      def abandon(self, app: AppLayout) -> None: ...
  ```
- Behavior spec:
  - detect: runs every stack's `detect` (stacks without one skipped) and picks the highest
    confidence above 0.5; adds bull's own issues: git submodules (block), nested git repositories
    (fix), branches or tags that
    clash with `module/*`, `feature/*`, `adopt/*` (fix), active git hooks (note), dirty tree (fix),
    not the root of its own repo (block). No stack found → issue (block) "no stack recognizes this
    project".
  - apply(stack): writes the detected (or chosen) stack and its settings into `config.toml`.
  - start: refused unless on a clean trunk and no module exists (an app the pipeline already built
    is refused); `status.start_adoption`, commits `chore: start adoption`, creates and switches to
    `adopt/main`.
  - legacy: files in the part's source folder outside `Modules/` and not in the memo's `App shell`
    list; declarations named `Legacy…` from the stack's `legacy_declarations` (if any); test files
    in the test folder outside module test folders and not in `App shell tests` (an `App shell` or
    `App shell tests` entry ending in `/` covers everything under that folder); files named in any
    module's `Legacy files` or `Legacy tests` that still exist.
  - finish: refused unless the adoption track is at stage 6 and `legacy` is empty (listing what is
    left); then `status.finish_adoption`.
  - abandon: on the trunk; clears the adoption; carries over backlog items queued on `adopt/main`
    (as features.abandon does).
  - cli: `bull adopt start|legacy|finish|abandon`; `bull stack detect [--apply [<stack>]] [--json]`
    prints the report (issues as `block|fix|note: item — fix`), exit 1 when blocked.
- Construction (internal; not contracts):
  - adopt.py: `LiveAdoption(files: Files, git: Git, runner: Runner, stacks: StackRegistry, ops:
    StackOps, parts: Parts, memo: MemoReader, settings: Callable[[AppLayout], Settings], store:
    Callable[[AppLayout], StatusStore], refs: Callable[[AppLayout], Refs])`; the callables are
    called after any write that changes what they read (e.g. `settings(app)` after `ops.select`).
    detect.py and legacy.py hold the logic as functions taking those collaborators.
  - detect: stacks from `stacks.all(include_test=True)` (journey 5 adopts with the fixture stack)
    with `optional.detect`; a stack whose detect raises is skipped. The winner's
    `Detection.issues` come first, then bull's in this order and wording (`Issue(level, item, fix)`):
    not the root of its own repo (`git.toplevel(root) != root`, incl. not a repo) → block
    "not the root of its own git repository", "run bull from the repository root, or `git init`";
    each submodule → block "git submodule <path>", "remove the submodule or vendor its files";
    each nested git repository (a folder below `root` holding a `.git` file or folder, found by
    walking the tree without entering `.git` folders, `__pycache__` or a found nested repo, and
    leaving out the submodule paths), sorted POSIX relative paths → fix "nested git repository at
    <path>", "remove its `.git` or vendor its files";
    each clashing branch (`git for-each-ref --format=%(refname:short) refs/heads/module/
    refs/heads/feature/ refs/heads/adopt/` through `runner`; a non-zero exit raises `GitError`
    "git for-each-ref failed: <stderr>", "check that git works in this repository") → fix "branch <name> clashes with
    bull's branch names", "rename or delete it"; each clashing tag (`git.tags` for `module/*`,
    `feature/*`, `adopt/*`) → fix "tag <name> clashes with bull's tag names", "rename or delete
    it"; each `git.active_hooks` entry → note "active git hook <name>", "bull's gates do not run
    it"; not `git.is_clean` → fix "uncommitted changes", "commit or stash them". Repo checks other
    than the first are skipped when the first fails. No stack → `stack`/`detection` None and the
    block issue "no stack recognizes this project", "pick one with `bull stack detect --apply
    <stack>` or `bull stack select`" placed first.
  - apply(app, report, stack): `stack or report.stack` (neither → `BullError`); `ops.select(app,
    name)`; then, only when that name is `report.stack`, each `report.detection.settings` entry
    via `settings(app).set(key, value, Layer.APP, None)` in mapping order. No commit.
  - start: trunk is `refs(app).trunk()`; refused (`BullError`) when not on it, the tree is not
    clean, or `store(app).load()` has any module, checked in that order, each message naming the
    problem and its fix: "adopt start runs on the trunk <trunk>; you are on <branch>" with fix
    "git switch <trunk>"; "adopt start needs a clean tree" with fix "commit or stash your
    changes"; "this app already has modules; adoption is for apps built outside bull"; then `start_adoption`, `git.commit_all(root,
    "chore: start adoption")`, `git.create_branch(root, "adopt/main", trunk, switch=True)`.
  - legacy: the app's one part (`parts.get(app, None)`); paths relative to `app.root`, POSIX,
    sorted, no duplicates. `files`: under `part.source_dir`, outside `Modules/`, not in
    `App shell`; `declarations`: the stack's `legacy_declarations(part.root)` names starting with
    `Legacy`; `tests`: under `part.test_dir`, outside module test folders (`parts.module_tests`
    of each memo module) and not in `App shell tests`; `memo_files`: `Legacy files`/`Legacy
    tests` entries of any module that exist. No memo file → no App shell lists and no memo_files.
    `__pycache__` folders and dotfiles are ignored.
  - finish: refused unless an adoption is active at stage 6 ("finish needs stage 6 (verify)")
    and `legacy` is empty (message lists each left path, grouped by field); then
    `finish_adoption` and commit "chore: adoption finished".
  - abandon: refused when no adoption is active or not on the trunk; reads `backlog.json` from
    `adopt/main` with `git.show_file` (format per **Formats**; missing → nothing to carry);
    items whose slug is not on the trunk are appended with state `queued`, other fields kept, and
    the trunk's backlog is written with `files.write_json` only if something was added; then
    `abandon_adoption` and commit "chore: abandon adoption". The `adopt/main` branch is kept.
  - cli.py: `register(commands, adoption: Callable[[], Adoption], layouts: Layouts)` adds `adopt`;
    `register_detect(stack_leaves, adoption, layouts)` adds `detect` to the subcommands action of
    the `stack` command that stacks.cli owns (how cli hands it over is the cli module's wiring)
    (the root is `layouts.find(Path.cwd())`'s root, or the cwd outside an
    app); refusals are raised as `BullError` for `cli.main`. `legacy` prints one `<field>: <path>`
    line per entry or "Nothing left to replace."; `--json` prints the four lists. `stack detect`
    prints `stack: <name> (<confidence>) — <summary>` or `stack: none`, then one issue line each;
    `--json` is `{stack, confidence, summary, settings, issues: [{level, item, fix}], blocked}`;
    `--apply [<stack>]` calls `apply` after printing, unless blocked (then it writes "blocking
    issues; nothing applied" to stderr); `--apply` with no name applies the detected stack
    (`apply(app, report, None)`); an unblocked `--apply` outside a bull app raises `BullError`
    "`--apply` needs a bull app here", "run `bull init` in the app's folder, or cd into a bull app".
- Reference tests: v1-tests/test_adopt_status.py::test_start_needs_a_clean_tree_on_the_trunk, test_finish_waits_for_verify, test_abandon_keeps_the_trunk_and_carries_the_backlog, test_app_shell_tests_are_not_old_tests; v1-tests/test_adopt_detect.py::test_trunk_clashes_hooks_and_dirty_tree, test_submodules_block_and_nested_repos_need_fixing, test_apply_writes_the_detected_settings, test_json_and_blocking_issues
- Contract: see `docs/api/adoption.md` (generated; do not edit by hand)

### gates
- Purpose: the gate driver: runs a stack's gate steps per part, adds bull's own gates (`api`,
  `coverage`, `interface`, zero tests), records passes, reruns failed tests, decides after-merge
  skips, and runs journeys with service parts started and stopped.
- Depends on: foundation, gitrepo, events, settings, memo, stacks, parts, status, coverage, api, interfaces
- Files: Contracts/__init__.py, mocks/__init__.py | steps.py, passes.py, failed.py | driver.py, after_merge.py | journeys.py, report.py, cli.py
- Protocol (draft; lives in `Contracts/`):
  ```python
  class Gate(Enum):
      PREFLIGHT = "preflight"; SETUP = "setup"; BUILD = "build"; TESTS = "tests"; LINT = "lint"
      API = "api"; COVERAGE = "coverage"; INTERFACE = "interface"; JOURNEYS = "journeys"
  class Verdict(Enum): PASS = "pass"; FAIL = "fail"; ABORTED = "aborted"
  class GateMode(Enum):
      MODULE = "module"; FAST = "fast"; FAILED = "failed"; COVERAGE_REPORT = "coverage-report"
      ALL = "all"; AFTER_MERGE = "after-merge"; JOURNEYS = "journeys"

  @dataclass(frozen=True)
  class GateRequest:
      mode: GateMode; module: str | None = None; branch: str | None = None; skip_coverage: bool = False

  @dataclass(frozen=True)
  class StepResult:
      gate: Gate; part: str; module: str | None; verdict: Verdict
      labels: tuple[str, ...]; seconds: float; output_tail: str

  @dataclass(frozen=True)
  class GateRun:
      request: GateRequest; verdict: Verdict; steps: tuple[StepResult, ...]
      tests_run: int; failed_ids: Mapping[str, tuple[str, ...]]
      coverage: tuple[CoverageReport, ...]; recorded: bool; note: str

  @dataclass(frozen=True)
  class PassRecord:
      sha: str; branch: str | None; command: str; time: datetime; parts: tuple[str, ...]

  class Gates(Protocol):
      def run(self, app: AppLayout, request: GateRequest) -> GateRun: ...
      def coverage(self, app: AppLayout, module: str) -> CoverageReport: ...
      def render(self, run: GateRun) -> str: ...

  class PassRecords(Protocol):
      def record(self, app: AppLayout, sha: str, branch: str | None, command: str, parts: Sequence[str]) -> None: ...
      def get(self, app: AppLayout, sha: str) -> PassRecord | None: ...
  ```
- Behavior spec:
  - steps: a gate step = the manifest argv with placeholders filled and the step environment from
    **Data models**; run from the part folder; labels from `bull-fail:` lines; non-zero without
    labels → label "<step> failed (exit N)"; each step appends a `gate_step` event (gate, part,
    module, verdict, seconds); output kept in `.bull/results/<part>/<step>.log`, last 40 lines in
    `output_tail`.
  - Unknown module → refused before running ("did you mean …" / module list); a module branch
    whose module isn't in status → refused.
  - MODULE (`gates <M>`), on the module's part: preflight (exit 2 → ABORTED, nothing else runs),
    setup, build_test (full suite with coverage), then for the module: lint, api, coverage (unless
    `--skip-coverage`), interface; while adopting (stages 1–5) also journeys and
    `BULL_ADOPT_MODE=1`, `BULL_SCOPE_MODULE=<M>`.
  - build_test results: the stack's `test_results(results)`; None or count 0 → fail `tests` "no
    tests ran" (even on exit 0); failed ids → fail `tests` (labels = ids); non-zero exit with no
    failed tests → fail `build`. Failed ids replace `.bull/results/<part>/failed.txt`; a passing run
    empties it.
  - FAST: preflight, build_test_fast(M), lint, api; never coverage; never records.
  - FAILED: for each part with ids in `failed.txt`, rerun_failed with them (tests_run = the number
    of ids); nothing to rerun → fail `tests`, label "no failed tests recorded; run `bull gates <M> --fast`" (nothing
    is rerun); never records.
  - COVERAGE_REPORT: as MODULE but stops after coverage and prints the report; never records.
  - ALL: per part in name order: preflight, setup, build_test once, then for each of the part's
    modules in build order lint, api, coverage, interface; then interface snapshots
    (`check_interface`) and `interfaces.problems`; then journeys for each part whose stack has
    `journeys`. With `--skip-coverage`, coverage is skipped and nothing is recorded.
  - JOURNEYS: journeys only, for every part whose stack has them; a part without them is reported
    "no journey tests" and skipped.
  - Journeys of a part: first starts each of `interfaces.parts_to_run(part)` (spawn `start` with a
    free 127.0.0.1 port, poll `ready` every 0.5 s until exit 0 or `ready_timeout` → fail `journeys`
    "<part> not ready"), passes `BULL_URL_<PART>=http://127.0.0.1:<port>`, runs `journeys`, then
    always runs `stop` and stops the spawned process (also when the journeys fail or raise); no
    process is left.
  - Pass recording (MODULE, ALL, AFTER_MERGE without skips): only when every step passes and the
    tree was clean before and after the run; writes `.bull/passes/<sha>.json`; a dirty tree →
    `recorded` false, note "not recorded: working tree has changes"; a failing run records nothing.
  - AFTER_MERGE(branch), on the base after a merge: when the branch head has a pass record and the
    paths changed between the branch head and HEAD all lie under `bookkeeping_paths`, record a pass
    for HEAD without running (note "merge holds the gated code"); otherwise run ALL.
  - coverage(M): report from the last full run's data in `.bull/results/<part>/` (none → error "run
    `bull gates <M>` first"). The exclude list passed to coverage is the resolved `coverage.exclude`
    followed by `coverage.exclude_extra` (extras add to the defaults, never replace them).
  - render: one line per step (`✓`/`✗ gate part [module] — labels`), failing output tails, the
    coverage report (when it lists files without coverage data, followed by one hint line naming the
    marker in the part's stack comment syntax, e.g. `add "# coverage-exempt-file: <reason>" in the
    first 10 lines of a file that only declares types`), failed ids, then "recorded" or the note. `--json` gives `GateRun` as JSON.
    Exit 0 on pass, 1 on fail, 2 on aborted.
- Construction (internal; not contracts):
  - steps.py (unit 2): `PLACEHOLDERS` = python, stack_dir, app_root, part_root, results, module,
    module_src, module_tests, port, failed_ids. `fill(argv: Sequence[str], values: Mapping[str,
    str], failed_ids: Sequence[str] = ()) -> list[str]`: an argument that is exactly
    `{failed_ids}` becomes one argument per id (none → removed); every other `{name}` of
    `PLACEHOLDERS` inside an argument is replaced from `values` (a name missing from `values` →
    empty string); any other text, braces included, is kept as is. `step_env(base:
    Mapping[str, str], app: AppLayout, part: Part, stack: Stack, results: Path, settings_json:
    str, adopt: bool, scope_module: str | None) -> dict[str, str]`: `base` (normally
    `os.environ`) plus `BULL_PART`, `BULL_PART_ROOT`, `BULL_APP_ROOT`, `BULL_RESULTS`,
    `BULL_STACK_DIR` (`stack.home`), `BULL_ADOPT_MODE` (`1`/`0`), `BULL_SCOPE_MODULE` (module or
    ""), `BULL_SETTINGS`; paths absolute. `settings_json(settings: Settings, part: str | None) ->
    str`: `{r.key: r.value for r in settings.show(part)}` as JSON, keys sorted, tuples as lists.
    `StepOutput` (frozen): `exit: int, labels: tuple[str, ...], tail: str, seconds: float`.
    `LiveSteps(runner: Runner, events: EventLog, files: Files)`:
    `execute(step: str, argv: Sequence[str], cwd: Path, env: Mapping[str, str], results: Path) ->
    StepOutput` runs `runner.run(argv, cwd, env, None)`, writes stdout then stderr to
    `results/<step>.log` (`files.write_atomic`; a line break goes between them when both are
    non-empty and stdout doesn't end in one), labels = each stdout line starting `bull-fail:`
    with the prefix and surrounding spaces removed, in order; non-zero exit and no labels →
    `("<step> failed (exit N)",)`; `tail` = the log's last 40 lines. `result(gate: Gate, part: str,
    module: str | None, verdict: Verdict, labels: Sequence[str], seconds: float, tail: str) ->
    StepResult` builds the result and appends one `gate_step` event (data: gate value, part,
    module or None, verdict value, seconds); every step bull reports, its own gates included,
    goes through it.
  - passes.py (unit 2): `LivePassRecords(files: Files, clock: Clock)`; record writes
    `app.passes_dir / "<sha>.json"` per **Data models** (time = `clock.now()`, naive treated as
    UTC); get: missing file, invalid JSON, not an object, `format` ≠ 1, or a missing/mistyped
    field → None (never raises), else the `PassRecord` (time timezone-aware UTC).
  - failed.py (unit 2): `read_failed(files: Files, results: Path) -> tuple[str, ...]` (lines of
    `results/failed.txt`, blanks and surrounding spaces dropped; missing → `()`),
    `write_failed(files: Files, results: Path, ids: Sequence[str]) -> None` (one id per line with
    a trailing newline; no ids → empty file).
  - driver.py (unit 3): `LiveGates(files: Files, git: Git, runner: Runner, events: EventLog,
    clock: Clock, stacks: StackRegistry, parts: Parts, triage: CoverageTriage, api: ApiSnapshots,
    passes: PassRecords, journeys: JourneyRunner, settings: Callable[[AppLayout], Settings],
    store: Callable[[AppLayout], StatusStore], refs: Callable[[AppLayout], Refs], memo:
    Callable[[AppLayout], Memo], interfaces: Callable[[AppLayout], Interfaces], python: str =
    sys.executable, environ: Mapping[str, str] | None = None)` (`environ` None → `os.environ`);
    it builds its own `LiveSteps(runner, events, files)`.
    - Modules come from `store(app).load().modules` (build order); a module's part is
      `parts.get(app, status.part or None)`, its stack `stacks.get(part.stack)`; the settings part
      argument is None for the implicit part (no `app.parts_dir / "<name>.toml"`), else the name.
      Results folder `app.results_dir / part.name`, created (parents too) before the part's
      first step. Placeholder values: python, `stack.home`, `app.root`, `part.root`, results,
      module, `parts.module_src`/`module_tests` (absolute; "" without a module).
    - Unknown module: a name matching one case-insensitively → `BullError("unknown module <m>",
      "did you mean <M>?")`; else fix "modules: a, b, c" (none → "this app has no modules
      yet"). MODULE/FAST/COVERAGE_REPORT without a module, or other modes with one → `BullError`;
      AFTER_MERGE without a branch → `BullError("gates --after-merge needs a branch", "run
      `bull gates --after-merge <branch>`")`.
      Module branch: `refs(app).module_for_branch(git.current_branch(root))` naming a module
      not in status → `BullError("branch <b> is for module <m>, which is not in status", "run
      `bull status init-modules` or switch branch")`; a detached HEAD (no current branch) skips
      this check.
    - Adopting = `status.adoption` set with stage ≤ 5. MODULE, FAST and COVERAGE_REPORT steps get
      `adopt=True, scope_module=M` only while adopting; ALL, JOURNEYS and FAILED steps get `adopt`
      while adopting and never a scope.
    - Step verdicts: exit 0 → pass, else fail; preflight exit 2 → `ABORTED` and nothing more runs
      (in ALL: no later part either). A setup failure stops that part's remaining steps, its
      journeys included (ALL goes on with the next part). build_test (and build_test_fast) gives a `TESTS` step and, on a
      non-zero exit with no failed ids, a `BUILD` fail step first; when it passes, one `BUILD`
      pass then `TESTS`; the `TESTS` step's seconds are the run's, `BUILD` 0. Failed ids
      (`TestRun.failed`) are written with `write_failed` after every build_test and
      build_test_fast (none → emptied). `tests_run` sums `TestRun.count`; `failed_ids` holds only
      parts with ids. Coverage is skipped (no step) when that part's build or tests failed. Every
      other step still runs after a fail, so one run shows every problem.
    - Bull's own steps: `API` from `api.check(app, M)` (not ok → labels ("contract differs from
      docs/api/<M>.md",), tail = the diff's last 40 lines); `COVERAGE` from `coverage(app, M)`
      (not clean → labels ("coverage not clean for <M>",); the report goes into `GateRun.coverage`
      whether clean or not); `INTERFACE` (module) from `interfaces(app).check_module(app,
      memo(app), M)` (labels "<interface>: <item> — <fix>" per failed item; no results → pass).
      ALL's app-wide `INTERFACE` step (part "", module None) collects `api.check_interface` of
      every `memo.interfaces` entry (labels "interface <Name> differs from its snapshot") and
      `interfaces(app).problems(memo)` as labels. seconds = measured wall time.
    - Journeys go through `journeys.run(...)` (journeys.py); a part whose stack has no
      `gates.journeys` gets no step (JOURNEYS mode adds "no journey tests: <part>" to the note).
    - Verdict: ABORTED if any step aborted, else FAIL if any failed, else PASS. Recording (MODULE,
      ALL, AFTER_MERGE, not `skip_coverage`): `git.is_clean(root)` before the first step and after
      the last, verdict PASS → `passes.record(app, git.head(root, "HEAD"), current branch,
      command, parts run)` (no commit at HEAD → `BullError("no commit at HEAD", "commit before
      recording a gate pass")`) with command "gates <M>", "gates --all" or "gates --after-merge
      <branch>"; notes, the first that applies: failed/aborted → "not recorded: gates failed";
      skip_coverage → "not recorded: coverage skipped"; dirty → "not recorded: working tree has
      changes"; FAST, FAILED,
      COVERAGE_REPORT, JOURNEYS → "not recorded: partial run (<mode value>)" (FAILED with nothing
      to rerun: verdict FAIL, one `TESTS` fail step (part "", module None, seconds 0) with that label, note
      "no failed tests recorded"; JOURNEYS notes joined with "; ").
    - FAILED: parts in `parts.all` order; a part with ids → one `TESTS` step from rerun_failed
      (`fill(..., failed_ids=ids)`); pass → `failed.txt` emptied; fail → replaced by
      `test_results(results).failed` when that returns ids, else kept; tests_run = number of ids.
    - coverage(app, M): no `test_results(results)` for the module's part → `BullError("no coverage
      data for <M>", "run `bull gates <M>` first")`; exclude = `coverage.exclude` +
      `coverage.exclude_extra` (part's settings; for these and `bookkeeping_paths` a string value
      counts as a one-item list, "" as empty, any other non-list → `BullError("setting <key> must
      be a list of strings")`); `triage.sources(parts.module_src(part, M),
      part.root, manifest.source_glob, exclude)`, `stack.readers.uncovered(part.root, sources,
      results)`, `triage.report(M, sources, data, manifest.comment)`. LiveGates remembers each
      reported module's stack comment for render.
    - render delegates to `report.render(run, triage, comments)` (`comments`: module → comment
      remembered by this instance; unknown → "#").
  - after_merge.py (unit 3): `after_merge_skip(app: AppLayout, branch: str, git: Git, passes:
    PassRecords, bookkeeping: Sequence[str]) -> PassRecord | None`: branch head
    (`git.head(root, branch)`; None → `BullError("no branch <branch>")`) has a record and every
    `git.changed_paths(root, head, "HEAD")` path is bookkeeping → that record, else None. A
    bookkeeping entry ending in `/` matches paths under it; otherwise the exact path or paths
    under `<entry>/`. LiveGates: a record → `passes.record` for HEAD with the record's parts and
    command "gates --after-merge <branch>", a `GateRun` with no steps, tests_run 0, recorded
    True, note "merge holds the gated code"; None → an ALL run whose request stays AFTER_MERGE.
  - journeys.py (unit 4): `JourneyRunner(runner: Runner, steps: LiveSteps, clock: Clock, sleep:
    Callable[[float], None] = time.sleep, free_port: Callable[[], int] = <bind 127.0.0.1:0>)`;
    `run(part: Part, stack: Stack, env: Mapping[str, str], values: Mapping[str, str], results:
    Path, providers: Sequence[Provider], adopt: bool) -> StepResult` where `Provider` (frozen) =
    `part: Part, stack: Stack, env: Mapping[str, str], values: Mapping[str, str], results:
    Path`, built by the driver from `interfaces(app).parts_to_run(memo, part.name)`. Per
    provider in order: port = `free_port()`, `runner.spawn(fill(run.start, values+port),
    provider.part.root, provider.env, results/"run.log")`, then `runner.run(fill(run.ready, …))`
    every 0.5 s (`sleep`) until exit 0 or `clock.now()` passes start + `ready_timeout` → `JOURNEYS`
    fail, labels ("<provider> not ready",), journeys not run. Then `execute("journeys", …)` with
    `BULL_URL_<PROVIDER UPPER>=http://127.0.0.1:<port>` added to `env`. In a `finally`, for each
    started provider (reverse order): `runner.run(fill(run.stop, …))` (errors ignored) and
    `spawned.stop(5.0)`. The step's part is `part.name`, module None.
  - report.py (unit 4): `render(run: GateRun, triage: CoverageTriage, comments: Mapping[str, str])
    -> str`: per step `✓`/`✗`/`!` (aborted) `<gate> <part>[ <module>]` (empty part left out) and
    ` — <labels joined by "; ">` when it has labels; then per failed/aborted step with a tail
    `--- <gate> <part> output ---` and the tail; then each coverage report with `triage.render`,
    followed (when it has no_data) by the hint `add "<comment> coverage-exempt-file: <reason>" in
    the first 10 lines of a file that only declares types`; then `failed tests (<part>):` and one
    id per line; then "<n> tests run"; last "recorded" (plus the note on the next line when
    non-empty) or the note. `run_json(run: GateRun) -> dict[str, object]`: dataclass fields,
    enums by value, paths POSIX strings, coverage reports with `clean` added, exemption `lines`
    null for whole-file.
  - cli.py (unit 4; decisions-log convention): `register(commands, gates: Callable[[], Gates],
    app: Callable[[], AppLayout], triage: Callable[[], CoverageTriage]) -> None` adds `gates` and
    `coverage`. `gates`: exactly one of `<M>`, `--failed`, `--all`, `--after-merge <branch>`,
    `--journeys`; `--fast`/`--coverage-report` only with `<M>` (not together); `--skip-coverage`
    only with `<M>` or `--all` (not with `--fast`/`--coverage-report`); else `BullError`. Prints
    `render(run)` or, with `--json`, `run_json(run)`; exit 0 pass, 1 fail, 2 aborted. `coverage
    <M> [--json]`: `triage.render(report)` or the report as JSON; exit 0 clean, else 1.
- Reference tests: v1-tests/test_gate_speed.py::test_skips_when_the_merge_holds_the_gated_code, test_ungated_bookkeeping_commits_on_the_base_still_skip, test_runs_everything_when_the_base_moved, test_runs_everything_without_an_earlier_gated_commit, test_runs_everything_when_another_module_changed, test_runs_everything_when_the_branch_head_was_not_gated, test_reruns_only_what_failed, test_a_passing_run_clears_the_list, test_module_runs_are_scoped_only_while_adopting, test_zero_tests_fail_the_run; v1-tests/test_gates_and_coverage.py::test_only_full_runs_record_a_pass, test_dirty_tree_records_nothing, test_failures, test_exclude_extra_adds_to_default; v1-tests/test_parts.py::test_gates_run_the_module_part, test_gates_all_covers_every_part, test_failed_tests_rerun_in_their_part, test_unknown_module_names_the_right_one, test_ui_tests_only_where_the_stack_defines_them; v1-tests/test_adopt_gates.py::test_full_runs_add_journey_tests_while_adopting, test_normal_app_and_stage_6_use_the_normal_gates, test_failing_journey_test_fails_the_run, test_no_modules_yet
- Contract: see `docs/api/gates.md` (generated; do not edit by hand)

### stacktest
- Purpose: a stack's self-test: the static shape check and the real run of `cases.json` against its
  fixture.
- Depends on: foundation, gitrepo, stacks
- Files: Contracts/__init__.py, mocks/__init__.py | cases.py, static.py | runner.py, cli.py
- Protocol (draft; lives in `Contracts/`):
  ```python
  class CaseVerdict(Enum): PASS = "pass"; FAIL = "fail"; NOT_RUN = "not run"

  @dataclass(frozen=True)
  class Case:
      id: str; change: Mapping[str, object]; run: tuple[str, ...]
      expect: Mapping[str, object]; then: "Case | None"

  @dataclass(frozen=True)
  class CaseResult:
      id: str; verdict: CaseVerdict; expected: str; got: str

  @dataclass(frozen=True)
  class StackTestReport:
      stack: str; static: bool; problems: tuple[str, ...]; cases: tuple[CaseResult, ...]
      @property
      def ok(self) -> bool: ...

  class StackTester(Protocol):
      def load_cases(self, stack: Stack) -> list[Case]: ...
      def static(self, stack: Stack) -> StackTestReport: ...
      def run(self, stack: Stack, case: str | None = None) -> StackTestReport: ...
      def render(self, report: StackTestReport) -> str: ...
  ```
- Behavior spec:
  - load_cases: parses `cases.json` (**Data models**); malformed → `StackError` with the reason.
  - static: required files (`stack.toml`, `readers.py`, `rules.md`, `setup.md`, `cases.json`,
    `fixture/`, which must not be empty), the manifest loads (no `TODO`), `readers.py` defines the required functions
    (checked with `ast`, without importing; a top-level `def`, import or assignment counts), `rules.md` has `## common`, `## outline` and one section
    per manifest agent, `setup.md` has `## For a feature`, `cases.json` has every required id;
    each miss is one problem. Needs no toolchain.
  - run: any `requires` tool missing → every case NOT_RUN ("missing uv: <the requirement's hint>"); a fixture file the layout
    names missing → NOT_RUN. For each case: copy the fixture into a fresh temp folder by `layout`,
    write `.bull/` with `bull init`-equivalent files for the stack (status at stage 5 with modules
    from the fixture memo), commit, apply `change` (a change whose `replace`/`delete` path doesn't
    exist → FAIL "change does not apply"), commit unless the case says `"dirty": true`, run
    `bull <run…> --json` as a subprocess (the bull command is a constructor argument), compare with
    `expect`; `then` runs in the same folder afterwards. Temp folders removed afterwards.
  - run: a `layout` that is not a folder→folder object, or `settings` that is not an object →
    `StackError`; an `expect` key other than verdict/gate/output/recorded/ran → the case FAILs
    ("unsupported expect key `<key>`").
  - ok: no problems and every case PASS; NOT_RUN counts as failure.
  - render: each problem, each case with its verdict (expected/got for a failure, the reason for
    NOT_RUN), then a summary line "N passed, N failed, N not run".
  - cli: `bull stack test <name|path> [--static] [--case <id>] [--json]`; exit 1 unless ok; a path
    loads the folder with `registry.load_path`.
- Reference tests: v1-tests/test_stack_test.py (all except test_the_real_ios_stack_passes)
- Contract: see `docs/api/stacktest.md` (generated; do not edit by hand)

### stackflow
- Purpose: the staged workflow for building a stack in its own repo, its template, and `stack
  install`'s checks.
- Depends on: foundation, gitrepo, stacks, stacktest
- Files: Contracts/__init__.py, mocks/__init__.py | workflow.py, template/DESIGN.md, template/stack.toml, template/cases.json | install.py, cli.py
- Protocol (draft; lives in `Contracts/`):
  ```python
  class StackStage(IntEnum):
      DISCUSS = 1; SCAFFOLD = 2; FIXTURE = 3; GATE_CODE = 4; REVIEW = 5; ACCEPTED = 6

  @dataclass(frozen=True)
  class StackRepoStatus:
      format: int; name: str; stage: StackStage; checkpoints: tuple[str, ...]
      static_pass: str | None; test_pass: str | None   # sha of the last passing run

  class StackWorkflow(Protocol):
      def init(self, path: Path) -> StackRepoStatus: ...
      def load(self, path: Path) -> StackRepoStatus: ...
      def set_stage(self, path: Path, stage: int) -> StackRepoStatus: ...
      def checkpoint(self, path: Path, name: str) -> StackRepoStatus: ...
      def record_test(self, path: Path, report: StackTestReport) -> StackRepoStatus: ...
      def next_step(self, path: Path) -> str: ...
      def ref(self, kind: str, name: str) -> str: ...

  class StackInstaller(Protocol):
      def install(self, path: Path) -> Stack: ...
  ```
- Behavior spec:
  - init(path): name = folder name; refused when inside a bull app, the folder is non-empty, the
    name is invalid, `_template`, or a built-in stack's name; creates the folder, `git init`,
    `stack.toml` from the template with `name` filled and `TODO` placeholders, `DESIGN.md` titled
    `# <name> stack: design`, `cases.json` from the template,
    `.bull/status.json` `{format: 1, kind: "stack", name, stage: 1, checkpoints: []}`,
    `.gitignore`, commits `chore: bull init --stack`. It writes no provider files (`CLAUDE.md`,
    settings): `appinit` does that after calling it.
  - Stage rules: 2 needs `design-approved`; 4 needs a static pass at HEAD; 5 needs a full test pass
    recorded; checkpoint `rules-approved` needs stage 5; `accepted` needs `rules-approved` and a full
    test pass at HEAD on a clean tree; checkpoints: `design-approved`, `rules-approved`,
    `accepted`.
  - record_test: called by `bull stack test .` inside a stack repo; stores HEAD's sha as
    `static_pass` or `test_pass` when the report is ok and the tree is clean.
  - next_step: per stage ("discuss the design and fill DESIGN.md; then `bull status checkpoint
    design-approved`", "write the fixture and cases.json until `bull stack test . --static`
    passes", …).
  - ref: tags `stack/<checkpoint>`; branches `stack/<stage name>` (`stack/fixture`,
    `stack/gate-code`, …).
  - Template: `DESIGN.md` (sections: Language and tools, Contracts, Modules, Kind, Human setup,
    Adoption support, Interfaces and running, Decisions log; no build checklist — the status file
    tracks progress), `stack.toml` (every key, `TODO` values except `maturity = "experimental"`), `cases.json` (every required id with
    empty `change`). `bull template design` prints DESIGN.md.
  - install(path): `stack test --static` must pass (else refused listing problems), then
    `registry.install`; the installed stack keeps its manifest maturity.
  - cli: in a stack repo, `bull status [next|stage|checkpoint|ref]` act on the workflow;
    `bull stack install <path>`.
- Reference tests: v1-tests/test_stack_new.py::test_scaffolds_from_the_template, test_refuses_an_existing_name, test_refuses_an_invalid_name, test_refuses_the_reserved_template_name, test_refuses_inside_an_app
- Contract: see `docs/api/stackflow.md` (generated; do not edit by hand)

### hooks
- Purpose: the safeguards as provider-neutral decisions: session start, usage guard, merge guard,
  test protection, reference protection, agent start/end events.
- Depends on: foundation, gitrepo, events, settings, memo, usage, stacks, parts, status, gates
- Files: Contracts/__init__.py, mocks/__init__.py | merge_guard.py, protection.py | usage_guard.py, session.py, dispatch.py
- Protocol (draft; lives in `Contracts/`):
  ```python
  class HookKind(Enum):
      SESSION_START = "session-start"; BEFORE_AGENT = "before-agent"; BEFORE_SHELL = "before-shell"
      BEFORE_EDIT = "before-edit"; BEFORE_READ = "before-read"; AGENT_END = "agent-end"

  @dataclass(frozen=True)
  class HookEvent:
      kind: HookKind; cwd: Path
      agent: str | None          # subagent making the call; None for the orchestrator
      target_agent: str | None   # BEFORE_AGENT: the subagent type being launched
      prompt: str | None; command: str | None; paths: tuple[Path, ...]

  @dataclass(frozen=True)
  class HookDecision:
      allow: bool; message: str   # block reason, or context text (session start)

  class Hooks(Protocol):
      def handle(self, event: HookEvent) -> HookDecision: ...
      def merge_targets(self, command: str) -> list[str]: ...
  ```
- Behavior spec:
  - Outside a bull app (no layout found from `cwd`), and in a stack repo (its `status.json` has kind
    `"stack"`), every hook allows with an empty message.
  - A safeguard that fails (any exception, e.g. a corrupt `status.json` or a mistyped setting) fails
    closed: BEFORE_AGENT, BEFORE_SHELL, BEFORE_EDIT and BEFORE_READ block with "bull safeguard could
    not run: <reason>" (plus the fix when the error has one); SESSION_START and AGENT_END allow with
    that message.
  - Agent names compare by the part after the last `:` (`bull:code-writer` → `code-writer`).
  - SESSION_START: message = stage and mode, the paused unit and reason if paused ("run
    `/bull:resume`"), the waiting approval if any, and the next step.
  - BEFORE_AGENT: usage check PAUSE → block with its reason; waiting for an approval → block
    "waiting for the human to approve the <M> contract change"; UNKNOWN → allow with a warning;
    target `test-writer` or `code-writer` whose prompt mentions the reference folder
    (`reference_dir`, as `reference/` or the absolute path) → block "never give the reference folder
    to test-writer or code-writer"; otherwise allow and append `agent_start` (agent).
  - AGENT_END: append `agent_end`; allow.
  - BEFORE_SHELL: merge_targets(command) finds every `git merge` in the command (split on `&&`,
    `||`, `;`, `|`, newlines; redirections and `git -C <dir>` handled; `--abort`, `--continue`,
    `--quit` ignored; option values such as `-m <msg>` skipped; leading `VAR=value` assignments,
    wrapper words `env`, `command`, `exec`, `time`, `nohup`, `sudo` and shell keywords `{`, `!`,
    `then`, `do`, `else` skipped before `git`; `sh -c`/`bash -c` strings parsed in turn; `git merge`
    only inside a quoted argument, `git log --merges` and `git mergetool` are not merges) and returns
    the target refs. For each target: unknown ref → block "unknown ref <ref>"; no pass record for its head sha → block "no recorded full
    gate pass for <ref> at <sha>: run `bull gates …`"; a module branch whose module has reference
    tests and no scan → block "record the reference-test scan for <M> first". Block messages name
    only the ref, never fragments of the shell command (e.g. `2>&1`). Blocks append `hook_block`.
  - BEFORE_EDIT: agent `code-writer` editing a path that `parts.is_test_path` says is a test → block
    "code-writer may not edit tests".
  - BEFORE_READ: agent `test-writer` or `code-writer` reading a path inside the reference folder →
    block.
  - The reference rules apply only when the reference folder exists.
- Reference tests: v1-tests/test_merge_guard.py (all); v1-tests/test_parts.py::test_code_writer_kept_out_of_every_part_s_tests
- Contract: see `docs/api/hooks.md` (generated; do not edit by hand)

### plugin_text
- Purpose: the plugin's Markdown: orchestrator instructions, slash commands and agent definitions,
  stack-neutral and in `bull` terms.
- Depends on: none
- Files: Contracts/__init__.py, mocks/__init__.py, plugin_files.py | orchestrator.md | commands/discuss.md, commands/outline.md, commands/setup.md, commands/skeleton.md | commands/prototype.md, commands/build.md, commands/verify.md, commands/feature.md | commands/adopt.md, commands/resume.md, commands/status.md, commands/stack.md | agents/skeleton-builder.md, agents/screen-builder.md, agents/test-writer.md, agents/code-writer.md | agents/reviewer.md, agents/coverage-analyst.md, agents/journey-test-writer.md | agents/surveyor.md, agents/legacy-test-scanner.md
- Protocol (draft; lives in `Contracts/`):
  ```python
  @dataclass(frozen=True)
  class PluginFile:
      path: str; text: str      # path relative to the plugin root, e.g. "agents/reviewer.md"

  @dataclass(frozen=True)
  class AgentDoc:
      name: str; description: str; tools: tuple[str, ...]; model_setting: str  # "models.<name>"

  class PluginText(Protocol):
      def files(self) -> list[PluginFile]: ...
      def agents(self) -> list[AgentDoc]: ...
      def orchestrator(self) -> str: ...
  ```
- Behavior spec:
  - files: every Markdown file of the module, paths relative to the module (`orchestrator.md`,
    `commands/*.md`, `agents/*.md`), sorted.
  - agents: parsed from each agent file's frontmatter (`name`, `description`, `tools`); `model:`
    is not in the files (the provider adds it from `models.<name>`).
  - Every command file has frontmatter with `description`; every agent file has `name` equal to its
    file name, `description` and `tools`.
  - Text rules (checked by tests): commands and settings named in the text exist (`bull <command>`
    matches the **Commands** table, `/bull:<name>` matches a command file, `models.<agent>` an
    agent); no v1 names (`ios-pipeline`, `.pipeline/`, `pipeline-resume`, `ui-test-writer`); no
    language, toolchain or platform words (the `cli` module's banned list).
  - Content: rewritten from v1's Markdown per **v1 Markdown review** (source: the approved note
    `docs/process/plugin_text.md`): the orchestrator rules (golden rules, briefs, asking the
    human, the Stage 5 loop with the reference-test scan step, feature cycle, adoption, parts and
    interfaces, handing off), one command per stage plus adopt, feature, resume, status and the
    stack workflow (`/bull:stack`, which refuses outside a stack repo), and the nine agents (v1's
    ui-test-writer renamed journey-test-writer).
  - test-writer: before it reports, it runs the stack's formatter and lint on the test files it
    wrote or changed and fixes what they find, so a formatting slip never costs a gate attempt
    (stack-neutral wording; the stack's rules name the tools).
- Construction (internal; not contracts):
  - plugin_files.py: `LivePluginText(root: Path | None = None)`; `root` defaults to the module's own
    folder (`Path(__file__).parent`). files: `orchestrator.md`, `commands/*.md`, `agents/*.md` under
    `root` (nothing else: no `.py`, no other folders), read as UTF-8, paths POSIX relative to `root`,
    sorted by path. orchestrator: the text of `orchestrator.md`. Frontmatter = the lines between a
    first line `---` and the next `---` line; each `key: value`, value trimmed and stripped of one
    pair of surrounding `"` or `'`; `tools` split on `,`, entries trimmed, empty ones dropped.
    agents: one `AgentDoc` per agent file in path order, `model_setting = "models.<name>"`. An agent
    file without frontmatter or missing `name`, `description` or `tools`, or whose `name` differs
    from its file name → `BullError` naming the file (`agents/<file>`) and the problem; a missing
    `orchestrator.md` → `BullError` naming it.
  - Text-rule tests live in `tests/plugin_text/` and run over every real file (they pass on the
    skeleton placeholders and keep holding as units fill the files). Only code spans and fenced
    blocks are checked for commands: the first word after `bull ` is a top-level command of
    **Commands** (`init open doctor status feature adopt stack stacks gates coverage api part config
    migrate template hook statusline help`, or a flag such as `--version`); for `status`, `feature`,
    `adopt`, `stack`, `part`, `config`, `template` and `hook` a following bare lowercase word is one
    of that command's subcommands in the table (`status` may also be followed by a flag or nothing).
- Reference tests: v1-tests/test_cli_misc.py::test_every_agent_has_frontmatter_and_its_stack_rules_exist
- Contract: see `docs/api/plugin_text.md` (generated; do not edit by hand)

### claude_code
- Purpose: the provider seam's one implementation: everything specific to Claude Code.
- Depends on: foundation, settings, usage, hooks, plugin_text
- Files: Contracts/__init__.py, mocks/__init__.py | plugin.py, hooks_json.py, launch.py | hook_io.py, statusline.py, app_files.py
- Protocol (draft; lives in `Contracts/`):
  ```python
  @dataclass(frozen=True)
  class HookOutput:
      stdout: str; stderr: str; exit_code: int

  @dataclass(frozen=True)
  class StatusLineInput:
      cwd: Path; usage: UsageSample | None

  class Provider(Protocol):
      name: str
      def render_plugin(self, dest: Path, settings: Settings, version: str) -> Path: ...
      def launch_argv(self, app: AppLayout, extra: Sequence[str]) -> list[str]: ...
      def tool_check(self) -> CheckItem: ...
      def parse_hook(self, kind: HookKind, raw: str) -> HookEvent: ...
      def hook_output(self, kind: HookKind, decision: HookDecision) -> HookOutput: ...
      def parse_statusline(self, raw: str) -> StatusLineInput: ...
      def app_files(self, app: AppLayout) -> dict[Path, str]: ...
  ```
- Behavior spec:
  - render_plugin(dest): writes `.claude-plugin/plugin.json` (name `bull`, version), `commands/`,
    `agents/` (adding `model: <models.<agent>>` to each frontmatter unless `inherit`),
    `hooks/hooks.json`, and `orchestrator.md`; replaces `dest` completely each time.
  - hooks.json maps: SessionStart → `bull hook session-start`; PreToolUse on the agent-launch tool →
    `before-agent`; on Bash → `before-shell`; on Edit/Write/MultiEdit/NotebookEdit → `before-edit`;
    on Read/Grep/Glob → `before-read`; SubagentStop → `agent-end`.
  - launch_argv: `["claude", "--plugin-dir", <app>/.bull/plugin, *extra]`.
  - tool_check: `claude` on PATH → ok with `claude --version`; missing → fix "install Claude Code:
    https://docs.claude.com/claude-code".
  - parse_hook: Claude Code's hook JSON → HookEvent (cwd, `agent_type` of the calling subagent if
    present, the launched `subagent_type`, `prompt`, Bash `command`, file paths from `file_path`,
    `path`, `notebook_path`); malformed JSON → an allow-everything event of the kind with cwd `.`.
  - hook_output: block → exit 2 with the message on stderr; allow → exit 0; session start → the
    message on stdout.
  - parse_statusline: reads `cwd` (or `workspace.current_dir`) and the rate-limit fields (5-hour and
    7-day used percentage and reset time) when present → UsageSample; absent → usage None.
  - statusline (the `bull statusline` command): records the sample in the app found from `cwd`
    (none outside an app), prints one line: `bull · stage N[ · feature <slug>] · units d/t[ · <plan
    label> i/n] · 5h x% · wk y%` (missing parts omitted).
  - app_files: `.claude/settings.json` (statusLine command `bull statusline`, permissions allowing
    `Bash(bull:*)` and `Bash(git:*)`, env `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`) merged into an
    existing file without dropping the user's keys; `CLAUDE.md` with a marked block
    (`<!-- bull:begin -->…<!-- bull:end -->`) importing `@.bull/plugin/orchestrator.md`, replacing
    only that block in an existing file. No absolute paths.
- Reference tests: none.
- Contract: see `docs/api/claude_code.md` (generated; do not edit by hand)

### appinit
- Purpose: `bull init`, `bull open`, `bull doctor`.
- Depends on: foundation, gitrepo, settings, formats, stacks, status, adoption, stackflow, claude_code
- Files: Contracts/__init__.py, mocks/__init__.py | init.py, doctor.py, cli.py
- Protocol (draft; lives in `Contracts/`):
  ```python
  @dataclass(frozen=True)
  class InitResult:
      root: Path; created: bool; relinked: bool; adopting: bool

  @dataclass(frozen=True)
  class DoctorReport:
      items: tuple[CheckItem, ...]; stacks: tuple[tuple[str, tuple[CheckItem, ...]], ...]
      @property
      def ok(self) -> bool: ...

  class AppInit(Protocol):
      def init(self, path: Path, adopt: bool = False) -> InitResult: ...
      def open_argv(self, path: Path, extra: Sequence[str]) -> list[str]: ...

  class Doctor(Protocol):
      def run(self) -> DoctorReport: ...
  ```
- Behavior spec:
  - init(path) on a missing or empty folder: creates it, `git init` (branch `main`), `.bull/`
    (`config.toml` with `format = 1`, `status.json` via `status.create`, `backlog.json`), merges the
    machine-local lines into `.gitignore`, writes the provider's app files, commits `chore: bull
    init`.
  - init on an existing bull app (root or `.`) → relink: rewrites the provider's app files and
    `.gitignore` lines only; state files untouched; commits if anything changed.
  - init inside a subfolder of a bull app → refused before creating anything.
  - init on a non-empty folder that isn't a bull app: without `adopt` → refused ("not empty and not
    a bull app; to bring an existing app under bull use `bull init --adopt`"); with `adopt` → it
    must be a git repo root on a clean tree; adds `.bull/` and the files above, commits, then
    `adoption.detect` (prints the report; blocked → stops there, exit 1), `apply`, commit,
    `adoption.start`.
  - `--stack` → `stackflow.init`, then writes the provider's app files and commits them
    (`chore: bull init --stack provider files`).
  - open_argv(path): path must be a bull app or stack repo; checks formats; renders the plugin into
    `.bull/plugin/`; returns the provider's launch argv. CLI: prints it with `--print-command`,
    otherwise replaces the process with it (`os.execvp`).
  - Doctor.run: items for python ≥ 3.11, `uv`, `git`, the provider's tool check; per stack (all
    non-test stacks) its `requires` tools. `ok` = the core items pass (stack tools are
    informational). CLI exits 1 when not ok and prints each fix.
- Reference tests: v1-tests/test_cli_misc.py::test_subfolder_of_app_is_refused_before_anything_is_created, test_init_dot_relinks_the_current_app; v1-tests/test_gates_and_coverage.py::test_nested_repo_is_refused
- Contract: see `docs/api/appinit.md` (generated; do not edit by hand)

### cli
- Purpose: the composition root, the argument parser and `main`.
- Depends on: foundation, gitrepo, events, settings, formats, memo, usage, stacks, parts, status, features, coverage, api, interfaces, adoption, gates, stacktest, stackflow, hooks, plugin_text, claude_code, appinit
- Files: Contracts/__init__.py | wiring.py, main.py, help.py
- Protocol (draft; lives in `Contracts/`):
  ```python
  # Contracts/__init__.py declares nothing: no module depends on cli.
  ```
- Behavior spec:
  - wiring: builds every real implementation once per process (built-in stack roots =
    `Modules/stack_*/*/`), and the command table from each module's `cli.py` registration function.
  - main(argv) → exit code: dispatches; inside an app, every command except `init`, `doctor`,
    `help`, `--version`, `hook`, `statusline` and `migrate` first runs `formats.check` and loads
    settings (a `ConfigError` prints `file:line: key: message` lines, exit 1); hooks and statusline
    never fail the session (errors → allow / a plain line, details on stderr).
  - A `BullError` prints `bull: <message>` and `  fix: <fix>` on stderr, exit 1; any other exception
    prints a one-line summary and "please report this", exit 70.
  - `bull help` / no arguments: the command list grouped as in **Commands**; `--version`: version.
  - `--json` output goes to stdout only; nothing else is printed to stdout with it.
  - Neutrality test: no file under `src/bull/` outside `Modules/stack_*/` contains the banned words
    (case-insensitive, whole words): Xcode, Swift, SwiftUI, UIKit, iOS, iPhone, simulator, XCUITest,
    pytest, mypy, ruff, xcodebuild.
- Reference tests: none.
- Contract: see `docs/api/cli.md` (generated; do not edit by hand)

### stack_fixture
- Purpose: two small, fast, toolchain-free stacks for bull's own tests and journeys: `fixture` (a
  tool with journeys, detect and json-schema interfaces) and `fixture_service` (a service part with
  start/ready/stop). Maturity `test` (hidden from `bull stacks` without `--all`).
- Depends on: stacks
- Files: Contracts/__init__.py, tool.py | fixture/stack.toml, fixture/readers.py, fixture/rules.md, fixture/setup.md | fixture/cases.json, fixture/fixture/ | fixture_service/stack.toml, fixture_service/readers.py, fixture_service/serve.py | fixture_service/rules.md, fixture_service/setup.md, fixture_service/cases.json, fixture_service/fixture/
- Protocol (draft; lives in `Contracts/`):
  ```python
  # Contracts/__init__.py declares nothing: the stacks implement `stacks.Contracts.StackReaders`.
  ```
- Behavior spec (the fixture language):
  - Source files `*.fx`: each non-blank line not starting with `#` is a code line; `pub <decl>` lines
    in `Contracts/` are contract declarations; `field <name>: <type>` lines in `Contracts/` declare
    interface fields; a line containing `WARN` is a build warning; `LINT` a lint error; `pub
    Legacy<Name>` a legacy declaration.
  - Test files `tests/<module>/*.test` (and `tests/journey/*.test`): `pass <name>` / `fail <name>`
    are tests (id `<module>/<file>::<name>`); `covers <path>:<lines>` marks lines executed
    (`3,5-7`).
  - tool.py (`python -m bull.Modules.stack_fixture.tool <step> …`): preflight (exit 2 if
    `fixture.toml` at the part root says `broken_toolchain = true`), setup (`bull-fail: fixture.toml
    missing` when absent), build-test (fails on `WARN` with `bull-fail: warning <file>:<line>`;
    writes `results/tests.json` `{count, failed}` and `results/coverage.json` executed lines; honors
    `BULL_SCOPE_MODULE`; in adopt mode, `WARN` outside `Modules/` is ignored), build-test-fast
    `<module>`, lint `<module>` (`bull-fail: lint <file>:<line>`), rerun `<ids…>`, journeys, and for
    the service: start/ready/stop on a port.
  - readers: contract_declarations, test_results, uncovered (code lines minus covered ones; a file
    with no code lines has no data), check (`fixture.toml` present; `ok = false` in it → failing item
    "fixture.toml says not ok"), detect (confidence 0.9 when `fixture.toml` and `*.fx` files exist),
    legacy_declarations, interface_check (json-schema: provider/consumer `field` lines must equal the
    schema's `properties` names and types — `string`/`integer`/`boolean`; an extra field on the
    provider → item "provider has field `x` not in the schema").
  - serve.py: an HTTP server on 127.0.0.1:`<port>` answering `GET /health` 200; ready polls it; stop
    terminates it via its pid file in `{results}`.
  - Each stack's `cases.json` covers every required id for its capabilities and passes `bull stack
    test fixture` / `fixture_service` (tests run them end to end).
- Reference tests: none.
- Contract: see `docs/api/stack_fixture.md` (generated; do not edit by hand)

### stack_python_cli
- Purpose: the python_cli stack (Python 3.11+, uv, pytest + coverage.py, ruff, mypy --strict),
  with json-schema interface support. Maturity `experimental` until bull itself is accepted.
- Depends on: stacks
- Files: Contracts/__init__.py | python_cli/stack.toml, python_cli/readers.py, python_cli/gates.py | python_cli/schema_check.py, python_cli/rules.md, python_cli/setup.md, python_cli/lint/ruff.toml | python_cli/DESIGN.md, python_cli/cases.json, python_cli/fixture/
- Protocol (draft; lives in `Contracts/`):
  ```python
  # Contracts/__init__.py declares nothing: the stack implements `stacks.Contracts.StackReaders`.
  ```
- Behavior spec:
  - Settings: `source_dir` (`src/<package>`), `test_dir` (`tests`), `package`; `coverage.exclude`
    default `["*/mocks/*", "*/Views/*"]`.
  - gates.py: preflight (`uv` present, `uv sync` succeeds; else exit 2 with the fix); setup
    (`pyproject.toml` exists, package importable, Python ≥ 3.11); build-test (`uv run mypy --strict`
    on the source folder — any error → `bull-fail: mypy <file>:<line>`; then `uv run pytest` over
    the test folder minus `tests/journey` with coverage (`--cov`, `coverage json` into
    `{results}/coverage.json`) and `--junitxml={results}/junit.xml`; `BULL_SCOPE_MODULE` limits
    pytest to that module's tests); build-test-fast `<module>` (`pytest tests/<module>`, no
    coverage, junit); lint `<module>` (`ruff check` and `ruff format --check` on the module's source
    and tests; config: the app's own ruff config, else `lint/ruff.toml`; rule set without `N`);
    rerun (`pytest <node ids>`); journeys (`pytest tests/journey`).
  - readers.contract_declarations: `ast`-based: top-level public classes (name, bases, decorators
    `dataclass`/`Protocol`), their public methods as `def name(args) -> ret`, dataclass fields
    `name: type`, enum members, public functions, type aliases; private names skipped; formatting
    differences don't change the output.
  - readers.test_results: parses `junit.xml` (count, failed/errored node ids); missing → None.
  - readers.uncovered: reads `coverage.json` (missing lines per file); a source absent from the
    data → no_data.
  - readers.check: `uv` on PATH, `pyproject.toml`, package import, Python version.
  - readers.interface_check (json-schema, via schema_check.py, stdlib only): the module's
    `Contracts` must declare a dataclass named after the schema's `title`; field names and types
    (`str`/`int`/`float`/`bool`/`list[...]`/`X | None` for non-required) must match `properties`;
    each mismatch is an item naming the field and role.
  - rules.md, setup.md, DESIGN.md: rewritten from the approved note `docs/process/stack_python_cli.md`
    (module folders `Modules/<module>/Contracts/`, `mocks/`; `pyproject.toml` template; journeys as
    subprocess tests; how mocks for a consumed json-schema interface are written).
  - The fixture (a one-module counter CLI) and `cases.json` (every required id plus `journey`,
    `journey-failing`, `interface-drift`) pass `bull stack test python_cli` (tests run it when `uv`
    is available, else skip).
- Reference tests: none (v1 had none for this stack beyond the fixture).
- Contract: see `docs/api/stack_python_cli.md` (generated; do not edit by hand)

### stack_ios
- Purpose: the iOS stack (SwiftUI, Swift 6, Swift Testing, XCUITest; Xcode on macOS), with
  adoption support and the run hygiene settled in `/discuss`.
- Depends on: stacks
- Files: Contracts/__init__.py | ios/stack.toml, ios/readers.py, ios/swift_scan.py, ios/pbxproj.py | ios/xcresults.py, ios/gates.py, ios/simulator.py | ios/detect.py, ios/inventory.py | ios/rules.md, ios/setup.md, ios/lint/swiftlint.yml, ios/lint/swift-format.json | ios/cases.json, ios/fixture/
- Protocol (draft; lives in `Contracts/`):
  ```python
  # Contracts/__init__.py declares nothing: the stack implements `stacks.Contracts.StackReaders`.
  ```
- Behavior spec:
  - Settings: `project` (`App/<Name>.xcodeproj`), `scheme`, `source_dir`, `test_dir`,
    `ui_test_dir`, `unit_test_target`, `ui_test_target`, `simulator` (device name, default the
    newest available iPhone), `coverage.exclude` default `["*/Views/*", "*/Mocks/*"]`.
  - simulator.py: chooses one available simulator by name and newest runtime from `xcrun simctl
    list devices available -j`, by UDID; stores the UDID in `{results}/simulator.txt`; none →
    preflight exit 2 naming the setting.
  - gates.py: one destination `id=<UDID>`, `-parallel-testing-enabled NO`, `-derivedDataPath
    .bull/build/DerivedData`, `-resultBundlePath {results}/<step>.xcresult`; Swift 6 with warnings
    as errors, except in adopt mode (project language mode kept, `SWIFT_STRICT_CONCURRENCY=complete`,
    no warnings-as-errors; any warning in `Modules/` or a module test folder fails the build);
    build-test runs the unit test target only (`BULL_SCOPE_MODULE` → `-only-testing` that module's
    suites); build-test-fast `-only-testing` the module's suites (found by `struct|class <X>Tests` or
    `@Suite`); a "simulator busy" failure retries the run, at most 3 attempts; xcodebuild output goes
    to a log, with known launch noise filtered from the shown tail (kept in the log); test
    diagnostics collected only when a run fails; journeys run the UI test target with screenshots
    kept only for failures; `prune` command deletes `.bull/build/` and old result bundles.
  - xcresults.py: test count and failed test ids from the result bundle (`xcresulttool`), a runner
    that failed to launch is not a test, coverage via `xccov` asked for the path the bundle recorded.
  - swift_scan.py: line scanner for `Contracts/` declarations (protocols, structs, enums, classes,
    their public members, multi-line signatures joined); `legacy_declarations` = `Legacy…` types.
  - pbxproj.py, detect.py, inventory.py: parse `.pbxproj` (quotes, comments, target settings falling
    back to project settings, malformed input raises); detect the project, schemes, Swift version,
    synchronized folders vs groups, test targets, unsupported dependencies (`Podfile`, `Cartfile`,
    extra projects in a workspace → block); inventory of types and references.
  - readers.check: Xcode present, project and scheme exist, Swift 6 (Swift 5 allowed only while
    adopting), test targets include their folders, synchronized folders (groups fail), no nested git
    repos.
  - rules.md, setup.md, fixture SETUP.md: rewritten from the approved note `docs/process/stack_ios.md`.
  - The fixture's Xcode project is made once by hand (SETUP.md, at the start of this module); `bull
    stack test ios` passes every case on a Mac with Xcode (the test skips elsewhere).
- Reference tests: v1-tests/test_adopt_detect.py::test_parses_quotes_comments_and_settings, test_target_settings_fall_back_to_the_project, test_malformed_input_raises, test_no_project, test_synchronized_swift5_app, test_setup_fixes, test_unsupported_dependencies_block, test_types_and_references, test_finds_declarations_not_mentions; v1-tests/test_adopt_gates.py::test_only_module_and_module_test_warnings_count, test_swift5_is_allowed_only_while_adopting, test_test_targets_must_include_their_folders, test_groups_and_nested_repos_fail; v1-tests/test_gate_speed.py::test_failed_ids, test_count, test_a_runner_that_failed_to_launch_is_not_a_test, test_asks_xccov_for_the_path_the_bundle_recorded, test_other_modules_suites; v1-tests/test_cli_misc.py::test_selection, test_diagnostics_flag_only_when_set, test_busy_simulator_is_waited_for_and_retried, test_busy_retries_stop_after_three_attempts, test_xcode_launch_noise_is_hidden_but_logged; v1-tests/test_stack_test.py::test_the_real_ios_stack_passes
- Contract: see `docs/api/stack_ios.md` (generated; do not edit by hand)

## Interfaces
None: bull is one part.

## Unmapped reference tests
- v1-tests/test_config.py::test_matches_bash, test_reports_what_bash_reads_differently, test_literal_dollar_is_fine, test_single_quotes_and_warnings: v1's shell-sourced `KEY="value"` config; v2 config is TOML.
- v1-tests/test_bash_shell_scanners.py (all): the bash_shell stack is rebuilt through the stack workflow; its own self-test covers its scanners.
- v1-tests/helpers.py: test helpers, no behavior.

## v1 Markdown review
Each file in `reference/v1-docs/` and what happens to it.

| v1 file | Decision | Goes to |
| --- | --- | --- |
| orchestrator.md | rewrite | plugin_text `orchestrator.md` |
| commands/discuss, outline, setup, skeleton, prototype, build, verify, adopt, feature | rewrite | plugin_text `commands/` (same names) |
| commands/pipeline-resume, pipeline-status | rewrite | plugin_text `commands/resume.md`, `status.md` |
| .claude/commands/new-stack.md | rewrite | plugin_text `commands/stack.md` (runs in a stack repo, staged) |
| agents/* (9) | rewrite | plugin_text `agents/` (ui-test-writer → journey-test-writer) |
| docs/adopt.md | merge | this memo (adoption, gates, status) and plugin_text adopt/orchestrator; iOS details → stack_ios rules |
| docs/stacks.md | merge | this memo (stacks, parts, interfaces, stacktest, stackflow); stack-author guide (Stage 6) |
| stacks/README.md | rewrite | stack-author guide `docs/stacks.md` (Stage 6) |
| stacks/_template/DESIGN.md | rewrite | stackflow `template/DESIGN.md` |
| workflow/templates/outline.md | rewrite | memo `templates/outline.md` |
| workflow/templates/backlog.md | keep (renamed terms) | memo `templates/backlog.md` |
| stacks/python_cli/rules.md, setup.md, DESIGN.md, fixture outline | rewrite | stack_python_cli |
| stacks/ios/rules.md, setup.md, fixture/SETUP.md, fixture outline | rewrite | stack_ios |
| stacks/bash_shell/* (DESIGN, rules, setup, fixture outline) | keep as input | the bash_shell stack-workflow run (copied out of `reference/` before it is deleted) |
| README.md | rewrite | `README.md` for new users (Stage 6) |
| workflow-guide.md | rewrite | `docs/guide.md` (Stage 6) |
| ROADMAP.md | drop | its items are in **Later features** and the discussion notes |

## Decisions log
- 2026-11-05: v2 is a new project built by v1 from this spec; v1 frozen to bug fixes from memo approval — see docs/bull-v2-brief.md — approved by Nicholas Johnson
- 2026-11-05: one part, all Python (stack python_cli); config TOML; stacks declare gate steps as argv commands bull runs — see discussion notes — approved by Nicholas Johnson
- 2026-11-05: python_cli and ios built as modules; bash_shell through the stack workflow after the core works — approved by Nicholas Johnson
- 2026-11-05: stacks built in their own repos (`bull init --stack`), installable by path — approved by Nicholas Johnson
- 2026-11-05: one Python package holds the command and the plugin; `bull open` launches Claude Code with the plugin from the installed package; state in `.bull/` (status and backlog separate, JSON; config TOML) — approved by Nicholas Johnson
- 2026-11-07: journeys, MVP features, constraints and interfaces between parts in v2.0 — approved by Nicholas Johnson
- 2026-11-07: the core enforces "no tests ran" and reads failures from the stack's readers, so a stack can't pass an empty run by mistake.
- 2026-11-07: `bull feature …` and `bull adopt …` are top-level commands (journey text uses them; `bull feature plan` replaces `status feature plan`).
- 2026-11-07: contract approvals are recorded (`bull status wait/approve`) and `bull api --write` refuses a changed snapshot without one; a feature's listed contract change pre-approves exactly one write per module.
- 2026-11-07: the merge guard also blocks merging a module branch whose reference-test scan isn't recorded (journey 12).
- 2026-11-07: `CLAUDE.md` imports `@.bull/plugin/orchestrator.md`, rendered by `bull open` (git-ignored), so no committed file holds a machine-specific path.
- 2026-11-07: fixture stacks (`fixture`, `fixture_service`) ship as built-in stacks of maturity `test`, hidden unless `bull stacks --all`.
- 2026-11-07: README, CONTRIBUTING, LICENSE, `docs/guide.md` and `docs/stacks.md` are written in Stage 6 (code-writer from this memo; the human reviews), not as a module.
- 2026-11-07: rewritten v1 Markdown reaches code-writer through source notes. At the start of plugin_text, stack_python_cli and stack_ios, before any unit, the orchestrator writes `docs/process/<module>.md` from the v1 files that **v1 Markdown review** sends there: stack-neutral where the target is, in `bull` terms and v2 formats. The human approves each note like a memo section; test-writer and code-writer briefs list the note, never `reference/`. (Options weighed: code-writer reads named v1 files; the orchestrator writes the Markdown itself.)
- 2026-11-07: at `/setup`, `.pipeline/config.sh` changes to `APP_PACKAGE="bull"`, `APP_SOURCE_DIR="src/bull"`, `APP_TEST_DIR="tests"` (the human edits it).
- 2026-11-07: PyPI distribution name is `bullofkrete` (`bull` taken; `bull-pipeline` also free) — approved by Nicholas Johnson
- 2026-11-07: Stage 4 (prototype) skipped: the skeleton's `bull` entry point is a stub and the python_cli stack has no screen-builder rules, so there is nothing to try. `ui-approved` is tagged without a review; the command surface is first checked in Stage 5 (cli) and Stage 6 (journeys). (Options weighed: review the Commands table on paper; a throwaway help-only shell.)
- 2026-11-08: foundation coverage triage — four behaviors added to the spec rather than removed: temp-name retry in write_atomic, missing `cwd` not reported as ToolMissing, idempotent `stop`, and spawn's ToolMissing (same as run) — approved by Nicholas Johnson
- 2026-11-08: post-merge check during stage 5 is `ios-pipeline gates --all --skip-coverage` instead of `gates --after-merge`: main has no recorded gate pass (the skeleton never recorded one) and coverage of unbuilt stub modules cannot pass until they are built. Each module still passes its full gates with coverage before merging, and `gates --all` runs once after the last module — approved by Nicholas Johnson
- 2026-11-08: events coverage triage — `read` skips a line whose data values aren't str/int/float/bool/null (added to the spec); `read` failing on non-UTF-8 bytes is deferred to the time report (Later features) rather than reopening foundation — approved by Nicholas Johnson
- 2026-11-08: module `cli.py` convention (first set by settings; every later module follows it): `register(commands: argparse._SubParsersAction[argparse.ArgumentParser], <collaborators as zero-argument providers typed by protocol, e.g. settings: Callable[[], Settings]>) -> None` adds the module's command parsers; each leaf parser does `set_defaults(run=<fn>)` with `run(args: argparse.Namespace, out: TextIO) -> int` (exit code; `--json` writes JSON only to `out`). Providers, not instances, because `cli.main` builds the parser before it checks formats and loads settings. `cli.wiring` calls each `register`; `cli.main` calls `args.run(args, sys.stdout)`. Errors are raised as `BullError`/`ConfigError`, never printed by the module.
- 2026-11-08: formats spec clarifications (follow from the foundation contract and the Commands table; flagged to the human at the module boundary): an app file that isn't valid JSON/TOML → foundation's `FileFormatError` naming the path from `inspect`/`check`/`migrate`; a non-integer `format` (incl. `true`) counts as missing (None, migrated from 0); `bull migrate` prints `migrated <path>` per changed file; a missing migration step's fix is the upgrade command.
- 2026-11-08: memo reference scan — `section_items` matches the `## <heading>` ignoring case (v1's test_sections_and_lists did; added to the spec) — approved by Nicholas Johnson
- 2026-11-08: memo coverage triage — duplicate `## <heading>`: first wins and it is reported through a new contract field `Memo.parse_problems` (contract change approved; no dependent module built yet); an interface side without `<part> / ` and an interface `File` without `(<format>)` are reported by `problems()`; slugged or unknown lines in `## Legacy code` are ignored (spec'd) — approved by Nicholas Johnson
- 2026-11-08: stacks reference scan (covered 4, missed 0, contradicts 0, not-in-spec 4) — added to the spec: `bull stack check` without `--part` checks every part (heading per part, exit 1 if any fails), and every `bull stack` command rejects an unknown `--part` naming the known parts; left out: v1's `stack show` and the `(this app: …)` marker in `bull stacks` (`part list` shows part stacks) — approved by Nicholas Johnson
- 2026-11-08: stacks spec clarifications from coverage triage (flagged to the human at the module boundary): `select` refuses with `StackError`, writing nothing, when `config.toml` can't be edited safely; `rules` without a `## common` section returns the agent's section alone, and `rules(stack, "common")` returns that section once.
- 2026-11-08: parts spec clarifications from review (flagged to the human at the module boundary): a stack's slash-free `.gitignore` line keeps its any-depth meaning under a part folder (`__pycache__/` → `web/**/__pycache__/`; middle-slash lines → `web/<line>`; `/x` → `/web/x`); `part add` refuses a folder that resolves outside the app (symlinks followed), rolls back every write on failure, and creates the part's source and test folders; `part check` also reports missing source/test folders and bad `dir` values; `is_test_path` resolves paths and is false outside the app.
- 2026-11-08: parts reference scan (covered 8, missed 2, contradicts 2, not-in-spec 3, obsolete 1) — `part check` prints `no problems` on success; a stack's unanchored gitignore lines stay scoped to the part (`web/**/x`, not v1's unchanged copy); the spec line about moving `/`-anchored `.gitignore` lines on the first `part add` is deleted (v1 never did it; a no-op at `.`); `part add` refuses `dir` at or inside `.bull`, `.git`, `docs`, `interfaces` — approved by Nicholas Johnson
- 2026-11-08: status construction (store/refs constructors, model.py functions, store delegating to pure functions in transitions.py/modules.py) set in the status § "Construction" line; internal wiring, no contract change.
- 2026-11-08: status `attempt` at the limit saves the `blocked` state, then refuses (store raises after writing); found by the unit 2 code-writer.
- 2026-11-08: status reference scan (covered 14, missed 0, contradicts 0, not-in-spec 4, obsolete 4) — human: `init-modules --replace` keeps unchanged units' progress (v1 behavior; spec line added under init_modules); `bull status` shows no per-part lines (`bull part list` covers it); finish's "not adopted"/legacy-left refusals belong to the adoption module, already specified there.
- 2026-11-08: status coverage triage — human approved specifying and testing 12 code-writer guards (listed under status Behavior spec "Guards"). Open for the features module: a `Changes` line naming a file new to an existing module (no unit holds it yet) is refused by `reopen`; features must decide how new files join a module.
- 2026-11-08: status exemption review — refs and LiveProgress derive mode from one load; naive clock times are treated as UTC (they made every save fail); build order matches module blocks case-insensitively like memo problems. No contract change.
- 2026-11-08: features — human: a file new to an existing module goes where the feature's memo puts it in the module's `Files` groups (existing group → that unit; new group at the end → new unit), decided per feature. `feature plan` uses `status.init_modules(replace=True)` (keeps unchanged units) then `reopen`; no status change. Closes the open item from status coverage triage. Also: `feature list` position is the queued position `move` takes (`-` otherwise); `start` refuses an existing `feature/<slug>/main` branch before any write.
- 2026-11-08: features reference scan (covered 5, missed 1, contradicts 0, not-in-spec 4, obsolete 1) — human kept all four v1 behaviors: wrapped list-item continuation lines joined into the description, checkbox items (`[x]` skipped, `[ ]` stripped), `--section` matched case-insensitively, and the start-during-adoption refusal saying it can start after the adoption finishes. Missed: add works during an adoption. Obsolete: v1's (ideas, notes) return pair.
- 2026-11-08: features coverage triage — human approved specifying and testing 8 code-writer guards and the `plan` output text (listed under features Behavior spec "Guards" and "plan output").
- 2026-11-08: coverage reference scan (covered 5, missed 0, contradicts 0, not-in-spec 3) — human: a file marker on a file that has coverage data is reported as an invalid marker ("unnecessary file marker") so it gets tidied; gates' render adds a hint line naming the file marker in the stack's comment syntax when files lack coverage data (in gates, since coverage's `render` doesn't know the comment; no contract change); v1's "N declaration-only file(s) exempt" count left out; gates combines `coverage.exclude` + `coverage.exclude_extra` before calling coverage (reference case test_exclude_extra_adds_to_default moved to gates) — approved by Nicholas Johnson
- 2026-11-10: coverage coverage triage — human: specify and test the nested-begin invalid marker ("coverage-exempt-begin inside an open block") and the full-path exclude match for a source outside `part_root`; missed test: directories matching `source_glob` are not sources — approved by Nicholas Johnson
- 2026-11-10: api construction (LiveApiSnapshots collaborators, paths, diff labels, `approval.authorize` order, cli output) set in the api § "Construction" line; the `approved` note goes through `status.approve` so its `decision` event is logged by status (api gains no events dependency); internal wiring, no contract change.
- 2026-11-10: api coverage triage — human: specify and test parse refusing damaged snapshot text (missing heading, `## <path>` with no fence, unclosed block), the missing-interface-file error, and `--check` with `--write` refused — approved by Nicholas Johnson
- 2026-11-10: test-writer formats and lints its own test files before reporting (plugin_text Behavior spec; stack rules name the tools). From the v1 run: test-writers twice left a test file that failed the formatter, each costing a retry; until plugin_text ships, the orchestrator adds this to every test-writer brief — requested by Nicholas Johnson
- 2026-11-10: interfaces construction (LiveInterfaces collaborators, problem texts, check without interface_check, parts_to_run ordering) set in the interfaces § "Construction" line; internal wiring, no contract change.
- 2026-11-10: adoption construction (LiveAdoption collaborators, issue texts and order, apply via `select` + `Settings.set`, legacy path rules, abandon's backlog carry-over from `adopt/main`, cli output; `stack detect` registered through `register_detect` because stacks.cli owns `stack`) set in the adoption § "Construction" line; adoption now depends on settings (for `apply`); branch-clash listing goes through `Runner` because `Git` has no branch listing; internal wiring, no contract change.
- 2026-11-10: interfaces depends on settings (its Construction takes the app's `Settings`); added to its Depends line and the build order. settings is already built, so the order is unchanged.
- 2026-11-10: interfaces coverage triage — human: keep, specify and test the `parts_to_run` guard for a non-string `stack` setting (`BullError` "part <part>: the stack setting is not a name") — approved by Nicholas Johnson
- 2026-11-11: adoption reference scan (covered 13, missed 0, contradicts 2, not-in-spec 6, obsolete/out of scope 3) — human: dotfiles stay ignored by `legacy` (spec over v1); `App shell`/`App shell tests` entries ending in `/` cover their folder (v1); detect reports nested git repositories as a fix issue (v1); `stack detect --apply` takes an optional stack name, none → the detected stack (v1); `adopt start` refusals name the problem and fix (v1); a blocked `--apply` writes "blocking issues; nothing applied" to stderr (v1); left out: abandon printing carried-over items (would change the `abandon` contract) — approved by Nicholas Johnson
- 2026-11-11: adoption coverage triage (missed 4, not-in-spec 2) — human kept and specified both: `stack detect --apply` outside a bull app is refused (`BullError`); a failed `git for-each-ref` in detect raises `GitError`. Missed: abandon's malformed `adopt/main` backlog (`FileFormatError`: bad JSON, no `items`, item without `slug`) and `adopt` subcommands outside an app — approved by Nicholas Johnson
- 2026-11-11: gates construction (LiveGates collaborators and per-app providers, LiveSteps/fill/step_env, pass-record and failed.txt helpers, step order and skip rules, notes, after-merge skip, JourneyRunner lifecycle, render/JSON, cli flag rules) set in the gates § "Construction" line; journeys are injected into LiveGates as a JourneyRunner (unit 3 may stub it; unit 4 builds it); render's file-marker hint uses the stack comment LiveGates remembers from coverage; internal wiring, no contract change.
- 2026-11-11: gates unit 3 review — three choices the spec left open set in the gates § Construction: FAILED reruns get the adopt env (no scope) while adopting; a part whose setup failed gets no journeys; the not-recorded note is the first of gates failed → coverage skipped → working tree has changes. Internal behavior, no contract change.
- 2026-11-11: gates reference scan (covered 20, missed 0, contradicts 2, not-in-spec 0, obsolete 1) — human: `gates --after-merge` keeps the spec (skip when only bookkeeping differs from the gated branch head, even if the base was never gated; v1 also required a gated base); `gates --failed` with nothing recorded fails (v1) with "no failed tests recorded; run `bull gates <M> --fast`", since a build failure leaves the list empty; unreadable test results with exit 0 still fail "no tests ran" (spec, per 2026-11-07); v1's after-merge reason lines and "pass now" text left out — approved by Nicholas Johnson
- 2026-11-12: gates coverage triage (missed 3, not-in-spec 5) — human kept and specified all five: a detached HEAD skips the module-branch check; recording with no commit at HEAD raises `BullError("no commit at HEAD")`; `--after-merge` without a branch raises `BullError`; list settings (`coverage.exclude`, `coverage.exclude_extra`, `bookkeeping_paths`) accept a string as a one-item list and refuse other non-lists; step logs put a line break between stdout and stderr when stdout lacks one. Internal behavior, no contract change — approved by Nicholas Johnson
- 2026-11-12: stacktest unit 2 — `static`'s "manifest loads" check is self-contained (`tomllib`: the file parses, `format == 1`, required tables/keys present, no `TODO` value; each miss one problem naming `stack.toml`); enum/name rules are not rechecked because stacks' contract exposes no folder validator and the stack was already validated when loaded. A case's `"dirty": true` is carried in `Case.change["dirty"]` (the contract has no field); a `then` case's id is `<parent>/then`. No contract change — approved by Nicholas Johnson
- 2026-11-12: stacktest unit 3 construction — `LiveStackTester(bull: tuple[str, ...])` takes the bull command; `cli.register(stack_leaves, tester, registry)` adds `test` under the `stack` command (like adoption's `register_detect`), providers zero-argument; an argument with a path separator or naming an existing folder is a path, else a stack name; `--json` keys `stack`, `static`, `problems`, `cases[{id, verdict, expected, got}]`; `layout` keys are folders under `<stack>/fixture/`, the fixture memo is the app's `docs/outline.md`; the runner reads bull's JSON whatever its exit code (gates `run_json` shape: `gate` = failing step, `output` = substring of failing labels or check items, `ran` = `tests_run`); output that is not JSON → FAIL with the output in `got`; `--case <id>` runs that case and its `then`, an unknown id → `StackError`; a `then` runs unless its parent's change did not apply. Internal behavior, no contract change.
- 2026-11-12: stacktest unit 3 review — the runner runs `git` itself in its throwaway folders (fixed identity, `--no-verify`, `--initial-branch=main`; `GIT_DIR`/`GIT_WORK_TREE` and other `GIT_*` repo-location variables removed from the child env), so stacktest uses nothing from gitrepo; bull's and git's output are decoded with `errors="replace"`; no timeout on bull; `--static` with `--case` → `StackError`. Internal behavior, no contract change.
- 2026-11-12: stacktest reference scan (covered 9, missed 1, contradicts 2, not-in-spec 3, obsolete 2) — human: a report with NOT_RUN cases exits 1 like any not-ok report (spec; v1 exited 3); an empty `fixture/` is a static problem (v1); render ends with "N passed, N failed, N not run" (v1) and a missing tool's NOT_RUN reason carries the requirement's hint (v1); the failing run's raw output is not echoed (v1 did). Missed: an unknown `--case` id → `StackError` — approved by Nicholas Johnson
- 2026-11-12: stacktest coverage triage (missed 10, exempt 3, not-in-spec 3) — human kept and specified all three: a malformed `layout`/`settings` in cases.json → `StackError`; an unknown `expect` key fails the case; a required reader bound by a top-level assignment counts as defined in the static check — approved by Nicholas Johnson
- 2026-11-16: `bull init --stack`: stackflow.init creates the stack repo without provider files; appinit's `--stack` path writes them (stackflow can't depend on claude_code) — approved by Nicholas Johnson
- 2026-11-16: stackflow unit 2 review — choices the spec left open: a stack repo's `.bull/status.json` holds only format/kind/name/stage/checkpoints; `static_pass`/`test_pass` live in git-ignored `.bull/passes/stack.json` (missing or malformed → no pass), so recording a pass never dirties the tree and the clean-tree checks are plain `git.is_clean`; stages advance one at a time (going back allowed; 0 and 7 refused); stage 5 needs a recorded full pass (any sha); stage 6 needs `accepted`; a repeated checkpoint is a no-op checked before its rules; `ref` refuses unknown kinds, checkpoints and stage names; `init` is allowed inside a stack repo (only a bull app refuses), refuses a missing parent folder, and on failure removes what it wrote (a pre-existing empty folder is left empty); `load` raises `FileFormatError` on bad values. Internal behavior, no contract change.
- 2026-11-16: stackflow unit 3 construction — install.py: `check_static(tester: StackTester, registry: StackRegistry, path: Path) -> None` loads the folder (`registry.load_path`), runs `tester.static`; not ok → `StackError` listing every problem; `LiveStackInstaller(tester, registry).install(path)` = `check_static` then `registry.install(path)` (nothing installed on refusal). cli.py: `register_status(commands, workflow: Callable[[], StackWorkflow], root: Callable[[], Path])` adds the stack repo's `status [--json]` (name, stage number and name, checkpoints, static/test pass), `status next`, `status stage <n>`, `status checkpoint <name>`, `status ref branch|tag <name>` (all printing one result; refusals raised as `BullError`); `before_install(tester, registry)` (zero-argument providers) returns the `Callable[[Path], None]` that stacks.cli's `register(before_install=…)` takes, wrapping `check_static`; `design_template() -> str` returns `template/DESIGN.md` for `bull template design` (cli.wiring adds it to memo's templates). Choosing app vs stack-repo `status`, and calling `record_test` after `bull stack test .`, are `cli.wiring`'s job. Internal wiring, no contract change.
- 2026-11-16: stackflow reference scan (covered 6, missed 0, contradicts 1, not-in-spec 2, obsolete 2) — human: `bull init --stack` also writes `cases.json` from the template (v1 did); the template's `stack.toml` has `maturity = "experimental"` (pinned); init titles `DESIGN.md` `# <name> stack: design` — approved by Nicholas Johnson
- 2026-11-16: stackflow coverage triage (missed 2, not-in-spec 7) — human kept and specified all seven: a missing or malformed built-in template (DESIGN.md or other template file missing, no `name` line in the stack.toml template, no title line in the DESIGN.md template) → `BullError` with fix "reinstall bull" (init and `design_template`); `init` on a path that is an existing file → refused, nothing created; `set_stage` to the current stage is a no-op (nothing written); `record_test` with no commit at HEAD records nothing and returns the status unchanged. Missed: `load` refuses a status file that is not a JSON object or whose `name` is not a string (`FileFormatError`). Internal behavior, no contract change — approved by Nicholas Johnson
- 2026-11-16: hooks unit 2 construction — merge_guard.py: pure `merge_targets(command) -> list[str]` (quote-aware split; `-m`/`--message=`/`-s` values skipped; octopus merges return every ref); `MergeGuard(git, passes: PassRecords, refs: Refs, status: StatusStore, events: EventLog).check(app, command) -> HookDecision` (target resolved by `git.head`; the first blocking target blocks; one `hook_block` event per block; allow has an empty message). protection.py: `Protection(parts, settings).check(app, event) -> HookDecision` for BEFORE_EDIT/BEFORE_READ (others allowed); "inside the reference folder" is a path-component match; `reference_dir` relative to the app root or absolute. Internal wiring, no contract change.
- 2026-11-16: hooks unit 3 construction — `UsageGuard(usage, status: StatusStore, settings, events).check(app, event)` handles BEFORE_AGENT (order: usage PAUSE, waiting approval, reference mention; UNKNOWN allows with a warning; appends `agent_start` on allow); `SessionStart(status: StatusStore, progress: Progress).check(app, event)` always allows (stage of the active track, mode, pause line, waiting line, next step); `LiveHooks(layouts, session, usage_guard, merge_guard, protection, events)` finds the app with `layouts.find(event.cwd)`, routes each kind, appends `agent_end` itself, allows BEFORE_SHELL without a command. App-bound collaborators (Usage, StatusStore, Progress, EventLog) are built by `cli.wiring` for the app found from the hook's cwd. Internal wiring, no contract change.
- 2026-11-16: hooks unit 3 review — a failing safeguard fails closed (guarded kinds block with "bull safeguard could not run: <reason>"; session start and agent end allow with the message); in a stack repo every hook allows with an empty message, like outside an app (`LiveHooks` also takes foundation `Files` to read the status file's `kind`) — approved by Nicholas Johnson
- 2026-11-16: hooks reference scan (covered 13, missed 4, contradicts 0, not-in-spec 2, obsolete 1) — human: merge_targets is hardened against env assignments, wrapper words, shell keywords and `sh -c` strings; "unknown ref <ref>" wording and no shell fragments in block messages are pinned; missed cases (env assignment, quoted `git merge` in an echo, `git log --merges`, `git mergetool`) get tests from the spec — approved by Nicholas Johnson
- 2026-11-16: hooks coverage triage (missed 9, not-in-spec 1) — human kept and specified the one: in merge_targets, an unquoted `#` starting a word begins a comment (ignored, as the shell does). Missed cases are tested from the spec's quote-aware parsing (backslash escapes and line continuations, escapes inside double quotes), wrapper options and `--` (`sudo -u root`, `sudo -E`, `env --`), wrappers with no command after them, `sh`/`bash` without a `-c` string, a module branch absent from status, and Protection allowing other kinds — approved by Nicholas Johnson
- 2026-11-16: source note `docs/process/plugin_text.md` approved, with its six choices (§5): `/bull:stack` uses test-writer, code-writer and reviewer in `MODE: stack` with a "Stack files" spec section in `commands/stack.md`; legacy-test-scanner has `MODE: adopt` and `MODE: reference` and ends with a `COUNTS:` line; `/bull:prototype` has a no-screens path; verify's device test becomes "hands-on"; feature stage 6 records checkpoint `accepted` before `bull feature accept`; agents carry explicit `tools:` lists. Adoption survey starts from `bull adopt legacy` (no inventory command in v2.0; the stacks' `inventory` reader stays unused) — approved by Nicholas Johnson
- 2026-11-16: plugin_text construction (LivePluginText root and file set, frontmatter parsing, errors; text-rule tests over every real file, command check limited to code spans and fenced blocks) set in the plugin_text § Construction line; internal, no contract change.
