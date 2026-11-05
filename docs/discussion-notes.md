# BullOfKrete: discussion notes (Stage 1)

Running notes from `/discuss`, started 2026-11-05. The settled decisions in
`docs/bull-v2-brief.md` are not repeated here; these notes record what `/discuss` adds or settles.

## Purpose

BullOfKrete (`bull`) is version 2 of the agent pipeline: a Claude Code plugin that builds software in
six staged steps (discuss → outline → setup → skeleton → prototype → modules → verify), plus a feature
cycle and adoption of existing apps, using specialized subagents, automated gates and human
checkpoints. It does everything v1 does, rewritten from first principles from a spec, with a
stack-neutral core: every platform (iOS, Python, shell, …) is a stack, and stacks themselves are built
through the same staged loop as apps.

**Target user:** developers in general who use Claude Code and want it to build and extend apps
through a disciplined, test-first, staged process, whatever the app's language. bull is open-sourced
after v2.0 is accepted, so it must install and make sense for strangers, not only for its author (who
has three v1 apps to migrate).

## Stack

**One part, stack `python_cli`** (Python 3.11+, uv, pytest + coverage.py, ruff, mypy --strict).
Selected 2026-11-05.

Why:
- v1 mixes Python (~3,900 lines: all logic) and shell (~1,250 lines: the `bin/` launcher, `gates.sh`
  per core and stack, shell-sourced `KEY="value"` config, two small hooks). The split is incidental,
  not principled: gate scripts call back into Python for anything hard, and shell config can't be
  validated and executes when loaded.
- v2 draws the line cleanly: **everything bull itself runs is Python**. Hooks and the status line are
  `bull` subcommands. Config is TOML (read natively, validatable; feeds roadmap item 5). A stack
  declares its gate steps as commands that bull runs and reads results from, instead of shell
  functions that get sourced.
- One set of gates and one coverage report covers all of bull's code.
- The two-part journey (7) is tested with a fixture app, not by making bull itself two parts.
- Rejected: two parts (`python_cli` + `bash_shell`): two setups, and parts can't call each other yet.

## Platforms

- macOS and Linux for the core. A stack may need a specific platform (the iOS stack: macOS with Xcode).

## Stacks in v2.0

A v2 stack is a self-contained folder: a TOML manifest declaring its build, test, lint, `--fast` and
`--failed` commands (bull runs them and reads their results), plus Python files for the contract
reader, coverage reader, `check` and optional `detect`. All its code is Python, like the core.

- **Shipped in v2.0, built now as ordinary bull modules** through the Stage 5 loop, with each stack's
  self-test (fixture + cases) part of its tests:
  - `python_cli`: needed so bull itself is the real app that makes it `verified`.
  - `ios`: needed to migrate the v1 apps.
- **`bash_shell` is rebuilt through v2's own stack workflow** once the core works: the real run of
  journey 6 and the workflow's first real test. If it isn't done when the rest of v2.0 is, it moves to
  later features rather than holding up v2.0.
- Rejected: building all three as modules (the stack workflow would only ever see a fixture); building
  only python_cli now (blocks migrating the iOS apps).

**Where stacks are built** (decided 2026-11-05):
- A stack is loadable from bull's built-in set or from a path or package (`bull stack install <path>`),
  so others can add stacks without forking bull.
- The stack workflow runs in the stack's **own git repo**, created by `bull init --stack`, with its own
  status file. Stages: discuss → scaffold → fixture and cases → gate code → review. Checkpoints:
  `design-approved` (DESIGN.md) and `rules-approved` (rules.md). Branches and tags like modules'
  (`stack/<step>`). Accepted stacks are `experimental` until one real app is accepted with them.
- A stack joins the built-in set by a PR to bull after passing `bull stack test`.
- Rejected: building stacks only inside the bull repo, tracked in bull's status file.

## Roadmap items (decided 2026-11-05)

In v2.0, as foundations that would be hard to add later:
- **Machine-readable output** (item 3's prerequisite): `--json` on status, backlog, usage and tags.
- **Event log** (item 4): append-only `.bull/events.jsonl` (git-ignored, machine-local), written by
  status changes, gate runs (per gate step) and subagent start/end hooks. No report yet.
- **Settings basics** (item 5): layered TOML (bull defaults → stack → user `~/.config/bull/` → app →
  part), validated on load and on write; `bull config show` (value and the layer it came from) and
  `bull config set`. Per-agent model is a setting. Expect settings to keep growing after v2.0; keep the
  schema easy to extend.
- **Provider seam** (item 6): everything Claude Code-specific (plugin files, hooks, launching,
  status-line usage, model names) in one `providers/claude_code` module behind an interface. Only
  Claude Code implemented.
- **iOS stack run hygiene** (from item 2, common-sense parts): one simulator chosen by UDID; no
  parallel testing, one destination; test diagnostics collected only on failure; UI test screenshots
  kept only on failure; build output and results under the app's `.bull/` instead of the global
  DerivedData, with a prune command.

## Install and files (decided 2026-11-05)

- **One Python package holds both the `bull` command and the Claude Code plugin** (commands, agents,
  hooks). Installed with `uv tool install <package>` (PyPI; from the GitHub repo before the first
  release). `bull open` starts Claude Code with the plugin files from the same installed package, so
  command and plugin versions always match. Updated with `uv tool upgrade <package>`; when an app's
  files are an older format, bull says so and points at `bull migrate`. `bull doctor` checks the
  install (uv, git, claude, stack toolchains).
  Rejected: plugin via the Claude Code marketplace (two things to update, can drift); git clone plus
  a `PATH` link as in v1 (awkward for strangers).
- **Names:** command `bull`, slash commands `/bull:<command>`. The PyPI package name is settled during
  `/setup` (`bull` is likely taken; fallbacks `bull-pipeline`, `bullofkrete`).
- **State files** (folder `.bull/` in each app):
  - committed: `status.json` (stage, checkpoints, modules, units, attempts, active feature or
    adoption) and `backlog.json` (feature queue), both JSON, written only by `bull`, atomically, with
    a `format` version. The backlog is separate because it is edited on `main` while a feature branch
    changes the status.
  - committed config (TOML, human-edited, validated): `config.toml`, plus `parts/<part>.toml` for
    multi-part apps; also with a `format` version.
  - git-ignored, machine-local: `usage.json`, `events.jsonl`, gate-pass records, run output.
  Rejected: everything in one status file (backlog edits on `main` collide with a feature's status
  changes); one status file per feature (more files; only one feature runs at a time).

## Open questions (from the brief)

1. ~~One part or two?~~ One part, all Python (see Stack).
2. ~~Existing stacks?~~ See Stacks in v2.0.
3. ~~Roadmap items?~~ See Roadmap items.
4. ~~Install and update?~~ See Install and files.
5. ~~Status file?~~ See Install and files.
6. ~~Names?~~ See Install and files.
7. ~~Stack builds?~~ See Stacks in v2.0.

## Core journeys

Draft 2026-11-05, for review. Journeys exercise `bull` as the orchestrator and hooks call it, run as
real subprocesses against temporary git repos. Subagents (Claude) are not part of the tests: where a
step is an agent's work, the test supplies the files that agent would write. Apps in journeys use a
small **fixture stack** (fast, no real toolchain) unless a journey says otherwise.

1. **Install and init.** Dana, a developer new to bull, runs `uv tool install <package>`, then
   `bull doctor` (reports uv, git and claude found; lists stacks and which toolchains are missing),
   then `bull init ~/apps/tally`. bull creates the folder, `git init`, `.bull/config.toml` and
   `status.json` at stage 0, the plugin settings and `CLAUDE.md`, and commits. `bull open ~/apps/tally`
   prints the `claude` command it launches with the plugin from the installed package; `bull status`
   says stage 0, next `/bull:discuss`.
   - Failure: `bull init` on a non-empty folder that isn't a bull app refuses and says why;
     on an existing bull app it relinks (safe to rerun) without touching state.
   - Failure: `bull doctor` with `claude` missing exits non-zero and names the fix.
2. **Build a small app end to end.** Dana builds `tally` with the fixture stack: `stack select`, stage
   changes 1→6, memo with two modules (`Store`, then `Counter` depending on it), `init-modules` from the
   memo, setup check passes → tag `setup`, skeleton gates pass → tag `skeleton`, checkpoint
   `ui-approved`; for each module: branch, unit tests → code → `gates --fast` → review → unit done,
   coverage report clean, full `gates <Module>` records a pass, merge, `gates --after-merge` (records
   without rerunning), `api --write`, tag `module/<Name>`; then `gates --all` and acceptance → tag
   `app-accepted`. `bull status --json` shows every unit done and every tag.
   - Failure: `status module Counter in_progress` before `Store` is done is refused (dependency).
   - Failure: a unit's 4th attempt is refused; the unit is `blocked` until the human decides.
3. **Pause on usage and resume.** Mid-build, the status line writes 5h usage at 92%. The orchestrator's
   `bull status usage-check` reports `PAUSE` with the reset time; the subagent-launch hook blocks the
   next agent with the same reason. Dana commits and runs `bull status pause "usage"`. Next day, in a
   fresh session, the session-start hook prints the stage, the paused unit and "run
   `/bull:resume`"; usage is back at 10%, `usage-check` reports `OK`, `bull status resume` clears the
   pause and `bull status next` names the same unit.
   - Failure: no usage data yet → `UNKNOWN`, proceeds with a warning (never blocks forever).
4. **Features from a file; build one, abandon one.** After `app-accepted`, Dana writes `ideas.md` with
   three ideas and runs `bull feature import ideas.md`: three backlog entries, each with a brief in
   `docs/features/`. `bull feature start reset-button` creates `feature/reset-button/main`; its memo
   marks `Counter` with `Changes (reset-button)` and a `Contract changes (reset-button)` line;
   `status feature plan` reopens only the unit holding the changed file. The unit runs the loop, the
   contract change passes `api` as pre-approved, verify, acceptance merges to `main` and tags
   `feature/reset-button/accepted`. Dana starts `dark-mode`, changes her mind, and runs
   `bull feature abandon dark-mode` on `main`: `main` is untouched, the backlog marks it abandoned.
   Meanwhile she added a fourth idea on `main` while `reset-button` was active, and the merge has no
   conflict (separate backlog file).
   - Failure: starting a second feature while one is active is refused; so is any feature before
     `app-accepted`.
5. **Adopt an existing app.** Sam has a small app built without bull (fixture stack, a few files,
   tests). `bull init --adopt .` detects the stack (`detect`), sets up `adopt/main`. The memo lists
   one module with `Legacy files:`, `Legacy tests:` and `Callers to repoint:`; baseline journey tests
   pass against the app as it is → tag `baseline`; scaffold → tag `scaffold`. The module's last unit
   is the switch-over (`status next` names it): legacy tests compared, callers repointed, legacy files
   deleted; full gates with journey tests pass; merge. `bull status adopt finish` → tags `adopted` and
   `app-accepted`; the app is an ordinary accepted app.
   - Failure: `adopt finish` while a legacy file listed in the memo still exists is refused.
6. **Add a stack through the stack workflow.** Lee wants a `go_cli` stack (a fixture stack in the
   test). `bull init --stack ~/stacks/go_cli` creates a stack repo with its own status at stage 1.
   DESIGN.md approved → tag `stack/design-approved`; scaffold from the template; fixture and
   `cases.json` written; `bull stack test . --static` passes; gate code written; `bull stack test .`:
   every case gives its expected verdict; rules.md approved → `stack/rules-approved`; accepted as
   `experimental`. `bull stack install ~/stacks/go_cli` makes it selectable; `bull stacks` lists it as
   experimental.
   - Failure: a gate that passes everything → the "failing test" case reports the wrong verdict, and
     `stack test` fails; a case the stack doesn't run reports "not run" and also fails.
7. **An app with two parts.** Ana's app has `cli` (fixture stack A) and `web` (fixture stack B):
   `bull part add cli <A> --dir cli`, `bull part add web <B> --dir web`. Each module has a `Part:`
   line; `gates <Module>` runs from its part folder with that part's stack; `setup` is tagged only when
   both parts pass `stack check`; `gates --all` runs each part, then journeys.
   - Failure: a memo where a `web` module depends on a `cli` module is refused by `init-modules`.
   - Failure: overlapping part folders reported by `part check`.
8. **A contract change stops the pipeline.** During `Counter` unit 2, the code-writer changes a
   method in `Counter/Contracts/`. `bull gates Counter --fast` fails the `api` gate with a diff of
   the contract against `docs/api/Counter.md`. The orchestrator sets the pipeline to waiting for
   approval; Dana approves; the decision is logged; `bull api Counter --write` updates the snapshot;
   gates pass.
   - Variant: inside a feature whose memo lists that change under `Contract changes (<slug>)`, the
     same diff passes without stopping; a further, unlisted change still stops.
9. **An unverified merge is blocked.** Dana (or the orchestrator) runs `git merge --no-ff
   module/Counter` on `main` after only `gates --fast`. The merge-guard hook refuses: no recorded full
   pass for the branch head. After `bull gates Counter` passes on a clean tree, the same merge goes
   through. A dirty working tree also blocks the record.
10. **Settings.** Dana sets `bull config set max_attempts 5` in her app; `bull config show` lists
    `max_attempts = 5 (app)`, `review_mode = combined (bull default)`, and the reviewer's model from
    her user layer. `bull config set max_attempts many` is refused with the allowed type; a hand-edited
    `config.toml` with an unknown key fails `bull status` with the file, line and key.
11. **Format versions.** Dana upgrades bull to a release whose status format is newer. Any `bull`
    command in her app stops with "this app's files are format 1; run `bull migrate`"; `bull migrate`
    upgrades the files, commits, and commands work again. An app whose format is newer than the
    installed bull is refused with "upgrade bull".

## MVP features

## Later features

- Windows support: hooks, paths and git behave differently; macOS and Linux first.
- GUI: a view across all apps, reading `--json` output (roadmap item 3); native macOS app or local web dashboard is open.
- Time report: `bull status time` totals by stage, module, unit, agent and gate step, from the event log (roadmap item 4).
- Settings page: GUI or screen for settings, beyond `bull config show/set` (roadmap item 5).
- Other AI providers: implementations behind the provider seam (roadmap item 6).
- Store readiness: optional stack release hook plus the iOS checks (privacy manifest, icons, permission strings, store-guidelines review) (roadmap item 7).
- Token report: tokens per stage, module, unit and agent (roadmap item 8).
- Automatic orchestrator restarts at module boundaries: bull drives `claude` from outside; needs its own design.
- Quieter iOS test runs (in limbo): simulator audio crackling seemed to resolve itself before the planned experiments ran. Remaining experiments: shut down simulators after every run (conflicts with reusing one booted simulator), report orphaned simulators at start, keep screenshots out of Photos and Spotlight (Spotlight Privacy as a manual setup step); open questions on clean-state launches and the speed cost of no parallel testing (roadmap item 2).

## Constraints

## Out of scope

- Reading v1 app files or formats automatically: only three v1 apps; migrated by hand.
- Changes to v1 beyond bug fixes: v1 is frozen from memo approval on.
- Adopting a multi-part app: not needed yet; adoption of one-part apps comes first.
- Splitting a part into its own app: not needed yet.
- Interfaces shared between apps: not needed yet.
