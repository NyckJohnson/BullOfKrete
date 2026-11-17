# plugin_text: source note

The content of the `plugin_text` module's Markdown, rewritten from v1's orchestrator, commands and
agents (memo **v1 Markdown review**) in `bull` terms, stack-neutral and in v2 formats. The memo's
`plugin_text` section says *what* the module is; this note says *what each file says*. test-writer
and code-writer read this note, never the v1 files. Approved by the human like a memo section;
changes after approval go through the decisions log.

How to read it: §1 holds the rules every file follows (names, commands, wording). §2–§4 give each
file's content, section by section, in the order the file should have them. Wording is the
code-writer's, in the style below; every rule, step, check and report field listed here must be in
the file, and nothing v1-only (§1.6) may be.

Style for every file: plain words, short sentences, second person to the agent ("You …"), imperative
steps. Command names, paths and settings in backticks. No emoji except the ✅/❌/✋ the steps name.

## 1. Rules for every file

### 1.1 Frontmatter
- Command files: YAML frontmatter with `description` (one line: "Stage N — …" for stage commands,
  as §3 gives it), plus `argument-hint` where §3 gives one. The body may use `$ARGUMENTS`.
- Agent files: frontmatter with `name` (= the file name without `.md`), `description` (as §4 gives
  it) and `tools` (comma-separated, as §4 gives it). **No `model:` line**: the provider adds it from
  the `models.<agent>` setting when it renders the plugin.
- `orchestrator.md` has no frontmatter; it starts with `# bull — orchestrator instructions`.

### 1.2 Names
| v1 | v2 |
| --- | --- |
| iOS Agent Pipeline, the pipeline | bull (the tool), the pipeline (the process) |
| `ios-pipeline <cmd>` | `bull <cmd>` (map in §1.3) |
| `/discuss` … `/verify`, `/adopt`, `/feature` | `/bull:discuss` … `/bull:verify`, `/bull:adopt`, `/bull:feature` |
| `/pipeline-resume`, `/pipeline-status` | `/bull:resume`, `/bull:status` |
| `/new-stack` (pipeline-repo command) | `/bull:stack` (runs in a stack repo) |
| ui-test-writer, UI tests, XCUITest | journey-test-writer, journey tests |
| `.pipeline/status.json` | `.bull/status.json` (and `.bull/backlog.json` for the backlog) |
| `.pipeline/config.sh`, `.pipeline/parts/<part>.sh` | `.bull/config.toml`, `.bull/parts/<part>.toml` |
| `.pipeline/usage.json` | `.bull/usage.json` (written by `bull statusline`) |
| `MAX_FILES_PER_UNIT`, `REVIEW_MODE`, retry cap 3 | `max_files_per_unit`, `review_mode`, `max_attempts` (default 3) |
| `APP_SOURCE_DIR`, `APP_TEST_DIR` | the part's `source_dir` and `test_dir` settings |
| `<APP_SOURCE_DIR>/Modules/<Module>/` | `<source_dir>/Modules/<Module>/` (per part) |
| `<APP_TEST_DIR>/<Module>/` | `<test_dir>/<Module>/` |
| `Mocks/`, `Views/` folders | "the module's mocks" / "view files", where the stack rules put them |
| `Contracts/` | `Contracts/` (core convention: `bull api` reads it) |
| "install on a real device" | "use the app the way its users will" |
| `docs/adopt.md` in the pipeline | the **Adopting an existing app** section of the orchestrator instructions |

### 1.3 Commands (every `bull …` named in the text must be in the memo's Commands table)
| v1 | v2 |
| --- | --- |
| `status summary` | `bull status` |
| `status unpause` | `bull status resume` |
| `status feature add/import/list/move/start/plan/accept/abandon` | `bull feature …` (same subcommands) |
| `status feature import … --only "<Title>"` | (no `--only`) queue each chosen item with `bull feature add "<Title>: <desc>"` |
| `status adopt start/legacy/finish/abandon` | `bull adopt …` |
| `stack show` | `bull config show` (the `stack` key) |
| `stack inventory` | **none**: see §5 question 1 |
| `stack new <name>` | `bull init --stack <path>` (run by the human, outside a session) |
| `gates --app-ui-tests` | `bull gates --journeys` |
| `git tag $(ios-pipeline status ref tag <x>)` | same with `bull status ref tag <x>` |
| contract change: stop and ask | `bull status wait <M> "<what>"` → ask → `bull status approve <M> "<note>"` → `bull api <M> --write` |
| (new) reference-test scan | `bull status refscan <M> --covered n --missed n --contradicts n --not-in-spec n` |
| (new) interface snapshot | `bull api --interface <Name> --write` |

All other v1 commands keep their names under `bull` (`status stage/checkpoint/init-modules/module/
unit/attempt/unblock/pause/plan/tick/ref/next/usage-check`, `gates …`, `api …`, `stacks`,
`stack select/rules/setup/check`, `stack detect [--apply]`, `part add/list/check`, `template …`).

### 1.4 Neutral wording (the `cli` module's banned words never appear)
Banned (whole words, any case): Xcode, Swift, SwiftUI, UIKit, iOS, iPhone, simulator, XCUITest,
pytest, mypy, ruff, xcodebuild. Also drop v1's platform-flavoured phrases:

| v1 | v2 |
| --- | --- |
| "for iOS: creating the Xcode project…" | "for example creating the project files the stack's tools need" |
| simulator or device | "the way its users will (the stack's setup guide says how)" |
| force unwraps | "crashing shortcuts (forced unwrapping, unchecked casts and the like)" |
| retain cycles | "reference cycles" |
| Dynamic Type, dark mode, launch time | "text sizes, appearance modes, startup work" (and "as the stack rules list") |
| `<File>.swift` | `<file>` |
| test files are "paths containing `Tests/`" | "test files (inside a part's test folder, or matching its stack's test pattern)" |
| a newer language mode | "the stack's full strictness" |

### 1.5 Settings named in the text
Only real keys: `max_attempts`, `max_files_per_unit`, `review_mode` (`combined`|`split`),
`base_branch`, `reference_dir`, `models.<agent>` (where `<agent>` is one of the nine agents),
`usage.pause_5h`, `usage.pause_weekly`. `bull config show` lists them; `bull config set` changes them.

### 1.6 Never in any file
`ios-pipeline`, `.pipeline/`, `pipeline-resume`, `pipeline-status`, `ui-test-writer`, `config.sh`,
`stack.sh`, `gates.sh`, `TaskCreate`, `--app-ui-tests`, "Swift's `Modules/…` shape", v1's
"no `STACK` line means iOS", and any absolute path.

## 2. orchestrator.md

Sections in this order.

1. **Intro.** You are the orchestrator for building an app in six stages (discuss, outline, setup,
   skeleton, prototype, modules, verify), with the stack chosen in stage 1 (`bull stacks` lists them).
   You talk to the human, own the memo and the status, run the gates and merge to the trunk.
   Subagents build; you never write app code yourself.
   **Where things live**: this session runs in the app's folder and git repo; bull and its plugin
   are installed once and shared; reach them only through `bull <command>`; never edit files outside
   the app folder (`.bull/plugin/` is rendered by `bull open`: never edit it).
   **Stacks**: everything language- or platform-specific (how gates build, test and lint, the
   contract reader, the manual setup, the agents' coding rules) comes from the stack. Follow its memo
   conventions (`bull stack rules outline`); each subagent reads its own rules with `bull stack rules
   <agent>`. Use the stack's terms with the human.
   **Parts**: an app can have several parts, each with its own folder and stack (`bull part list`).
   Then every module and journey has a `- Part:` line; briefs carry `PART: <name> (<stack>)`; agents
   read `bull stack rules <agent> --part <name>`; `bull gates <M>` runs in the module's part. A
   module never depends on a module of another part: parts talk only through **interfaces** (below).
   A one-part app needs none of this.
2. **Golden rules** (numbered):
   1. One subagent at a time; never in parallel.
   2. Files are the memory: `docs/outline.md`, `.bull/status.json`, `.bull/backlog.json`, git.
   3. Only you talk to the human; subagents return questions; follow **Asking the human**.
   4. Only you edit the memo, merge, and change status (through `bull status`; never hand-edit
      `.bull/` files).
   5. Contract changes need approval. A failed `api` gate (any change under a module's
      `Contracts/`, or to an interface file) stops the pipeline: `bull status wait <M> "<what>"`
      (bull then blocks agent launches), ask the human, and on approval `bull status approve <M>
      "<note>"` and `bull api <M> --write` (or `--interface <Name>`). `bull api --write` refuses a
      changed snapshot without an approval. Exception: a change listed as `Contract changes (<slug>)`
      in an approved feature memo is pre-approved once; any further change stops again.
   6. Attempts cap at `max_attempts` (default 3) across code → gates → review; `bull status
      attempt` blocks the unit at the cap; then ask the human (`bull status unblock` after they
      decide).
   7. Commit after every completed step.
   8. Stop at step boundaries: run `bull status usage-check` before every step; on `PAUSE`, commit,
      `bull status pause "<reason>"`, tell the human when usage resets, stop. `UNKNOWN` (no usage data
      yet) is a warning, not a stop.
3. **Files** table: `docs/outline.md` (memo; orchestrator), `docs/api/<Module>.md` and
   `docs/api/interfaces/<Name>.md` (snapshots; `bull api` only), `.bull/status.json` and
   `.bull/backlog.json` (bull only), `.bull/config.toml` and `.bull/parts/<part>.toml` (human, `bull
   config set`), `.bull/usage.json` (status line), `docs/features/<slug>.md` (feature briefs; `bull
   feature add/import` creates, orchestrator fills), `<source_dir>/Modules/<Module>/` (subagents:
   `Contracts/`, mocks, view files, implementation), `<test_dir>/<Module>/` (subagents),
   `interfaces/` (interface files; orchestrator or agents as the memo says), `reference_dir`
   (default `reference/`, read-only, only legacy-test-scanner reads it).
   **Progress gauge**: before a step with more than three items (prototype screens, verify, a long
   fix-up round), `bull status plan <label> <item>…`, mirror it as a task list, `bull status tick
   <item>` per item, `bull status plan <label> --clear` at the end. The status line shows it.
4. **Safeguards bull enforces** (new; one bullet each, so the orchestrator knows why a call is
   refused): usage guard (agent launches blocked on PAUSE); approval wait (agent launches blocked
   while waiting); merge guard (`git merge` of a branch needs a recorded full gate pass for its head,
   and, for a module with reference tests, a recorded scan); test protection (code-writer cannot edit
   test files); reference protection (test-writer and code-writer may not be given or read the
   reference folder). A safeguard that cannot run fails closed and says why: fix the cause, never work
   around it.
5. **Stages and commands** table: 1 Discuss `/bull:discuss` (notes ready; stack selected) · 2
   Outline `/bull:outline` (checkpoint 1: memo approved → tag `outline-approved`) · setup
   `/bull:setup` (`bull stack check` passes for every part → tag `setup`) · 3 Skeleton
   `/bull:skeleton` (gates pass → tag `skeleton`) · 4 Prototype `/bull:prototype` (checkpoint 2:
   flow approved → `ui-approved`) · 5 Modules `/bull:build` (each module merged → tag
   `module/<M>`) · 6 Verify `/bull:verify` (checkpoint 4: accepted → `app-accepted`).
   `/bull:resume` continues after a pause or in a fresh session; `/bull:status` reports. Adoption:
   `/bull:adopt`; after acceptance `/bull:feature`. Checkpoint 3 is any contract change, at any time.
   The human starts each stage; never start the next one yourself. `bull status next` always names
   the next step.
6. **Delegating to a subagent.** Every subagent starts with no memory; brief shape exactly:
   ```
   TASK: <one sentence>
   MODULE: <name>   UNIT: <n> (files: <a, b, …> or "n/a")   ATTEMPT: <n of max_attempts>
   PART: <name> (<stack>)   (only in an app with several parts)
   READ ONLY THESE:
   - docs/outline.md § <section names>
   - docs/api/<Dependency>.md (each dependency's contract; never its implementation)
   - <specific source or test files>
   ACCEPTANCE:
   - <checkable criteria>
   PREVIOUS FAILURE (if retry):
   <gate or review output, trimmed>
   RETURN: the report format in your agent definition.
   ```
   Optional lines the sections below add: `CHANGE: <slug>`, `ADOPT: …`, `LEGACY FILES`, `CALLERS`,
   `MODE: …`, `SCOPE: …`, `CATEGORIES: …`. Modules are folders, not enforced packages: the brief is
   the boundary (own module files plus dependency contracts); the reviewer checks for leaks. Never
   list the reference folder in a test-writer or code-writer brief (bull blocks it).
   **Units and context**: the memo splits modules with more than `max_files_per_unit` files into
   units. A test-writer or code-writer that runs short returns `STATUS: partial` with `DONE` and
   `REMAINING`; start a fresh one for the rest (no attempt used). Reports start `STATUS: done |
   partial | blocked`; on `blocked`, take its `QUESTION:` block (`ASK`, `WHY`, `OPTIONS`,
   `RECOMMEND`) to the human per **Asking the human**, never forwarded as-is.
7. **Asking the human** — v1's section, kept whole: the six parts (Where we are; What happened, with
   `file:line` quotes and one line per attempt after a cap; Why it needs you, naming the rule; Options,
   two to four, each with what changes, which modules, cost; Recommendation; What happens next per
   answer) and the rules (plain words, explain a pipeline term the first time; one decision per
   question, number several; repeat the one-line "where we are" inside a multiple-choice prompt;
   approvals follow the same shape: what to look at, what changed, what approving commits to; record
   answers that change the spec or a contract in the memo's decisions log).
8. **Stage 5 loop** (per module in build order, dependencies `done`). Branch and tag names from
   `bull status ref`: `base` (trunk = `base_branch`, or `feature/<slug>/main`, or `adopt/main`),
   `module <M>`, `tag <label>`.
   1. `git switch -c <branch> <base>`; `bull status module <M> in_progress`.
   2. Per work unit (one unless `Files:` is split with `|`), in order:
      1. **test-writer** → tests for every file in the unit, from the spec. `partial` → fresh
         test-writer for `REMAINING`. Commit `test(<M>): unit <n> tests`; `bull status unit <M> <n>
         tests`.
      2. **code-writer** → implementation; cannot edit tests.
      3. `bull gates <M> --fast`. Fail → `bull status attempt <M> <n>`, back to 2.2 with the output
         (code-writer may iterate with `bull gates --failed`, then confirm with `--fast`). `api`
         gate failure → golden rule 5. Pass → `bull status unit <M> <n> code`.
      4. **reviewer** with `SCOPE:` the unit's files; one combined pass (`review_mode = combined`,
         default) or one pass per category (`split`). Blocker findings → attempt, back to 2.2.
      5. Commit `feat(<M>): unit <n>`; `bull status unit <M> <n> done`.
   3. **Reference-test scan** (only when the module's memo block has a `Reference tests:` line;
      `bull status next` names it): **legacy-test-scanner** with `MODE: reference`, the module's spec,
      its new test files and the reference tests named on that line. `covered` → nothing; `missed` →
      test-writer writes the test **from the spec** (brief names the behavior, never the old test);
      `contradicts` and `not-in-spec` → ask the human, record the answer in the decisions log, then
      memo or test change as decided. Then `bull status refscan <M> --covered … --missed …
      --contradicts … --not-in-spec …` (counts from the scan) and commit. The merge guard refuses the
      module's merge until it is recorded.
   4. **Coverage triage**: `bull gates <M> --coverage-report`; uncovered lines → **coverage-analyst**
      with the report; `missed` → test-writer from the spec; `exempt` → the analyst added a
      `coverage-exempt` marker (line, block, or `coverage-exempt-file` for a declarations-only file),
      **reviewer** confirms it; `not-in-spec` → ask the human: remove the code, or add it to the spec
      and test it. Repeat until clean.
   5. `bull gates <M>` (full suite and coverage; the only run that records the pass the merge guard
      needs; needs a clean tree). Failures → owning subagent as in step 2 (attempts count);
      `bull gates --failed` while fixing, then this step again.
   6. `git switch <base> && git merge --no-ff <branch>`.
   7. `bull gates --after-merge <branch>` on `<base>` (records without rerunning when the merge holds
      exactly the gated code; otherwise runs `--all`).
   8. `bull api <M> --write`; the memo's `Contract:` line points at `docs/api/<M>.md`; commit.
   9. `git tag <tag>` (from `bull status ref tag module/<M>`); `bull status module <M> done`.
   After the stage's last module: `bull gates --all` on `<base>`; failures go to the owning module as
   in verify.
9. **Interfaces between parts** (new; from v1 `docs/stacks.md`'s design, now in the memo): the memo's
   `## Interfaces` names each interface file (`interfaces/<file>`, with its format), its provider
   `<part> / <Module>` and consumers. The file is a contract: `bull api --interface <Name> --write`
   snapshots it, a change stops the pipeline (golden rule 5). The `interface` gate checks each side
   with its own stack, so a consumer can be built and gated before its provider exists. Journeys that
   cross parts run with the provider parts started by bull. Never let a module import another part's
   code; if two parts need to talk, propose an interface to the human.
10. **Feature cycle** (after `app-accepted`) — v1's section in v2 terms: `/bull:feature` queues
    ideas (one, or a Markdown file) in `.bull/backlog.json`, each with a brief in `docs/features/`;
    one active at a time on `feature/<slug>/main`; merges to the trunk only when the human accepts.
    Stage and checkpoints belong to the feature (`bull status stage`/`checkpoint` act on it; refs
    prefixed `feature/<slug>/`). The memo marks the change: `- Changes (<slug>): <files>` and `-
    Contract changes (<slug>): …`; `bull feature plan` adds new modules and reopens only the units
    holding changed files. Reopened units run the Stage 5 loop with `CHANGE: <slug>` and the brief's
    "Agreed scope" (test-writer updates tests of changed behaviors and leaves the rest; code-writer
    changes the existing implementation; reviewer checks the change and that unchanged behavior still
    holds). Verify writes journey tests for new and changed journeys only, runs all, reviews the diff
    from the trunk in the whole app's context. Abandoning leaves the trunk untouched.
11. **Adopting an existing app** — v1's section in v2 terms (adopt branch `adopt/main`,
    `adopt/`-prefixed branches and tags except `adopted`; ends with `bull adopt finish`). Stages: 1
    detect and discuss · 2 survey and memo · setup (adopt variant) · 3 baseline (journey tests
    against the app as it is) · 4 scaffold (renames, contracts, mocks; no stubs) · 5 adopt modules ·
    6 verify (legacy check, the stack's final switch to full strictness). Checkpoints
    `outline-approved`, `setup`, `baseline`, `scaffold`, `adopted` (which also records
    `app-accepted`). The memo describes the app as it is: behavior specs follow today's behavior;
    contracts are redesigned; per module `Legacy files:`, `Legacy tests:`, `Callers to repoint:`;
    `## Legacy code` holds `App shell:`, `App shell tests:`, `Legacy folders:`, `Renames:`. Legacy
    code stays until its module replaces it; while adopting, `bull gates <M>` scopes to the module
    and also runs the journeys, holding module code to the full standard while legacy code only has
    to build and pass its tests. Stage 5 additions: briefs say `ADOPT: unit` and list `LEGACY FILES`
    (code-writer may read them; test-writer never does); each module's last unit is its
    **switch-over** (`bull status next` names it): (1) legacy-test-scanner `MODE: adopt` compares
    the module's old tests with its new ones — `contradicts`/`not-in-spec` to the human, `missed` to
    test-writer `ADOPT: legacy cases` then code-writer if they fail (attempts count); then `bull
    status unit <M> <n> tests`; (2) code-writer `ADOPT: switch-over` with `CALLERS` and `LEGACY
    FILES`, then test-writer `ADOPT: switch-over`, then `bull gates <M> --fast`; pass → `bull status
    unit <M> <n> code`; (3) reviewer `SCOPE: switch-over <M>`; commit; `bull status unit <M> <n>
    done`. Coverage triage, full gates (with journeys), merge, after-merge, snapshot and tag as
    usual. Features can be queued during an adoption but start only after it finishes. Adoption is
    for one-part apps.
12. **Handing off**: at the end of each stage, or when context gets long: "Good point to start a
    fresh session; run `/bull:resume` there." A new session rebuilds its picture from the memo,
    `bull status` and `git log`.
13. **Never**: use extra usage or an API key (stop and tell the human if usage is pay-as-you-go);
    delete branches, reset the trunk, force-push; start a feature before `app-accepted` or while one
    is active or during an adoption; improvise gates or tooling for a stack `bull stacks` doesn't
    list; edit tests to make code pass or code to make tests pass yourself; mark anything `done`
    that has not passed its gates; hand-edit `.bull/status.json` or `.bull/backlog.json`.

## 3. Commands

### commands/discuss.md
`description: Stage 1 — discuss the app's purpose, stack, journeys and constraints`;
`argument-hint: "[one-line app idea]"`. Body = v1's, in v2 terms:
- `bull status stage 1`; lead a conversation, one or two questions at a time, no questionnaire.
- Agreed by the end: purpose and target user; **stack** (`bull stacks`, one line each on what it
  builds and needs, recommend one; only listed stacks; `experimental` only when asked or nothing
  `verified` fits, saying they are new; unlisted → say it can be built as a stack with
  `bull init --stack` and `/bull:stack` in its own repo, then ask whether to continue with a listed
  one or stop); on agreement `bull stack select <name>`, commit `chore: select <name> stack`;
  **parts** when pieces use different stacks (`bull part add <name> <stack> [--dir <folder>]` each,
  instead of `stack select`; parts talk only through interfaces: agree which ones exist, their file
  format and provider/consumers); journeys (named user, goal, real steps, end state, failure paths);
  MVP vs later features (anything put off goes to later features, never dropped); constraints
  (minimum platform or runtime version, offline, accounts, sync, third-party services); out of scope
  with reasons.
- Running notes in `docs/discussion-notes.md`, committed as you go; `## Stack` (stack, parts and
  why), `## Later features` and `## Out of scope` as `- <Title>: <description or reason>` items (so
  `bull feature import` can queue them later). End: tell the human to run `/bull:outline`.

### commands/outline.md
`description: Stage 2 — write the outline memo and get it approved (checkpoint 1)`. v1's steps:
`bull status stage 2`; write `docs/outline.md` from the notes following `bull template outline`
exactly and `bull stack rules outline` (no stack in `bull config show` → back to the discuss step);
with parts: each part's rules (`--part`), parts under Constraints (`- Parts: a (stack), …`), a `-
Part:` line on every module and journey, dependencies inside a part, interfaces in `## Interfaces`.
Modules as folders, no-dependency first; `Files:` in build order split into units with `|` (at most
`max_files_per_unit`; contracts and models first); dependencies; draft protocol (lives in
`Contracts/`); view files where the stack rules say. "Anticipated operations"; build only what
journeys need plus cheap obvious complements; copy later features and out-of-scope into the memo.
**Rewrite of an existing tool** (new): when the app replaces an old one whose tests are kept as
reference (`reference_dir`), give each module a `Reference tests:` line and list unmapped old tests
under `## Unmapped reference tests` with a reason. Readiness list reported ✅/❌ (v1's eight items, with
"Screen list and navigation flow" reading "Screens (or command surface) and navigation"). Revise until
approved. On approval: `bull status init-modules` (check output; it refuses memo problems with line
numbers), commit `docs: outline approved`, `git tag outline-approved`, `bull status checkpoint
outline-approved`; tell the human to run `/bull:setup`.

### commands/setup.md
`description: Setup — walk the human through the stack's manual steps, then check them (between
outline and skeleton)`. v1's six steps: usage-check; memo approved (`outline-approved` in `bull
status`) else back to `/bull:outline`; `bull stack check` (every part, plus `bull part check`) —
passing → step 5; `bull stack setup` (`--part`, one part at a time), one step at a time with the
memo's real names, wait for "done", skip what the check shows done; settings the guide says to set →
confirm with the human, then `bull config set` (`--part`); re-check until all ✅, explaining each ❌
fix; can't fix → stop, don't continue; commit `chore: project setup`, `git tag setup`, `bull status
checkpoint setup`; tell them to run `/bull:skeleton`. Neutral example of a manual step: "creating the
project files the stack's tools need".

### commands/skeleton.md
`description: Stage 3 — build the compiling skeleton`. v1's steps: usage-check, `bull status stage
3` (refused without `setup`: then tell the human to run `/bull:setup`); with parts, once per part in
build order with `PART:` and only that part's modules; **skeleton-builder** brief points at the whole
memo and `.bull/config.toml` (and the part's `.bull/parts/<part>.toml`); `MANUAL STEPS FOR HUMAN` →
walk them as setup does, rerun gates. On `done`: `bull gates --all --skip-coverage` (all must pass);
`bull api <M> --write` per module and `bull api --interface <Name> --write` per interface; commit
`chore: skeleton`, `git tag skeleton`, `bull status checkpoint skeleton`; tell them to run
`/bull:prototype`. `blocked` or gates failing after `max_attempts` → report and stop.

### commands/prototype.md
`description: Stage 4 — build the UI on mocks for the human to try (checkpoint 2)`. v1's steps:
`bull status stage 4`; gauge `bull status plan prototype <screen>…`. Per screen: usage-check;
**screen-builder** (with `PART:`), the screen's memo entry, its journeys, protocols and mocks; `bull
gates --all --skip-coverage`, fix through the same agent (`max_attempts`); commit `feat(ui): <Screen>
prototype`; tick. Then the human tries the app (the stack's way: running it, or its previews) through
every journey; feedback list: screen/flow change → screen-builder, update the memo's screens section;
protocol change → checkpoint 3 (explain change, reason, affected modules; apply only after approval,
memo first). Repeat to approval: commit, `git tag ui-approved`, `bull status checkpoint ui-approved`,
clear the gauge, tell them to run `/bull:build`.
**No screens** (new): if the memo has no screens (a tool or service), say so, and with the human's
OK record the skip in the decisions log, commit, `git tag ui-approved`, `bull status checkpoint
ui-approved`.

### commands/build.md
`description: Stage 5 — build modules one at a time, foundational first`;
`argument-hint: "[module name to build only that one]"`. v1's text in v2 terms (this command's text
in v1 maps one to one): `bull status stage 5` (during a feature it sets the feature's stage;
branches and tags from `bull status ref`); `bull status next` (or `$ARGUMENTS`); follow the Stage 5
loop exactly with usage-check before every step; `--fast` while iterating, `--failed` reruns,
only full `bull gates <M>` records; `--after-merge` after a merge; `bull gates --all` once after the
last module. Stop and report when: all modules done → tell the human to run `/bull:verify` (feature
or adoption: continue with its stage 6 as `/bull:feature` or `/bull:adopt` says); PAUSE → pause; a
blocked unit, a contract change, a reference-scan or coverage finding that needs the human → ask.
Adoption: last unit is the switch-over, `ADOPT:` lines. Report to the human only at module
boundaries, one short line per module.

### commands/verify.md
`description: Stage 6 — test and verify the full app (checkpoint 4)`. v1's steps:
`bull status stage 6`; gauge `bull status plan verify mocks-check <one item per journey> app-review
fixes hands-on backlog` mirrored as a task list, tick each, clear at the end.
1. mocks-check: real implementations everywhere; mocks only in tests and previews (search for mock
   types used elsewhere).
2. usage-check, **journey-test-writer**: one journey test per memo journey (with parts, one brief
   per part whose stack has journeys, with `PART:` and that part's journeys); `bull gates
   --journeys`.
3. usage-check, **reviewer** `SCOPE: whole app` (with parts, every part listed): consistency across
   modules and the stack's whole-app items (the reviewer reads them from the stack rules).
4. Route each failure or finding to the owning module's unit and rerun its Stage 5 loop; if the
   design is wrong, propose a memo change first.
5. hands-on: the human uses the app the way its users will, through every journey; numbered list;
   each item **fix now** (route as 4), **later** (`bull feature add "<Title>: <what they said>"`) or
   **drop**; retest fixes; repeat; ask them to accept.
On acceptance: commit, `git tag app-accepted`, `bull status checkpoint app-accepted`.
6. backlog: `bull feature import docs/outline.md --section "Later features" --dry-run` and the same
   for `"Out of scope"`; two short lists plus what step 5 queued; ask which to queue and in what
   order; queue chosen ones with `bull feature add "<Title>: <desc>"` (`--top` where asked) and reorder
   with `bull feature move <slug> <pos>`; commit `docs: queue features after first release`; show
   `bull feature list`; ask whether to start the first now (`/bull:feature`, ideally in a fresh
   session) or later.
During an adoption `/bull:adopt` stage 6 replaces this; during a feature `/bull:feature` stage 6 does.

### commands/feature.md
`description: Add features after the app is accepted — queue ideas (one, or a file of them) and build
them one at a time`; `argument-hint: "[idea | path to a backlog file | nothing to continue]"`. v1's
structure (follow the orchestrator's Feature cycle; `bull feature --help` lists commands):
1. **Queue** `$ARGUMENTS`: a file path → `bull feature import <path> --dry-run`, show, then without
   `--dry-run` on OK; nothing found → show `bull template backlog`; an idea in words → `bull feature
   add "<Title>: <one line>"` (`--top` only if the human says so); nothing → step 2. Commit `docs:
   queue feature <slug>` on the current branch.
2. **Decide**: `bull status next`. Active feature → continue at its stage (switch branch first if
   `next` says so). App not accepted, or an adoption active → ideas stay queued; say so, stop. No
   active feature → `bull feature list`, confirm which (first queued unless the human picks or
   reorders with `bull feature move`); on a clean trunk `bull feature start [<slug>]` (it commits
   `chore: start feature <slug>` and switches to `feature/<slug>/main`).
3. **Stages** (usage-check before every step; `bull status stage/checkpoint` apply to the feature;
   tag with `git tag $(bull status ref tag <name>)`):
   1. Discuss from the brief's "Idea" and the memo; new/changed journeys with failure paths,
      screens, affected modules, contract changes, interfaces, out of scope; notes in the brief's
      "Discussion notes" and "Agreed scope"; commit as you go.
   2. Outline: edit the memo in place — new journeys get next numbers, changed ones edited in place;
      new modules at the right place in the build order; in each existing module the feature changes,
      `- Changes (<slug>): <files>` (every file whose behavior or code changes, including
      implementations that must follow a contract change) and the updated behavior spec; new files go
      in a new unit (append `| <file>` to `Files:`, never into a finished unit); a changed contract
      gets `- Contract changes (<slug>): <what>` (same for an interface's entry); a decisions-log
      line; remove the item from `Later features`/`Out of scope` if it came from there. Show the
      memo diff (`git diff <trunk> -- docs/outline.md`, trunk from `bull status ref trunk`) and the
      contract changes, saying approval approves those contract changes. On approval `bull feature
      plan` (check its output), commit `docs: feature <slug> outline approved`, `bull status
      checkpoint outline-approved`, tag.
   3. Manual setup only if needed (`bull stack setup --section "For a feature"`, `--part`), walk as
      `/bull:setup`, `bull stack check`, commit `chore(<slug>): project setup`; a feature adding a
      part: `bull part add`, then that part's whole setup. Skeleton only if `feature plan` says
      `Skeleton needed: yes`: skeleton-builder `MODE: feature <slug>` with the new modules and
      contract changes; `bull gates --all --skip-coverage`; `bull api <M> --write` per new or
      changed module (the listed change passes once as pre-approved); commit `chore(<slug>):
      skeleton`, `bull status checkpoint skeleton`, tag.
   4. Prototype only if screens are new or changed, as `/bull:prototype` for those screens; the
      real code doesn't do the new things yet (stubs), so the human judges them on mocks; say so. On
      approval commit, `bull status checkpoint ui-approved`, tag. Otherwise record the checkpoint
      with a note that nothing changed on screen.
   5. Build: the Stage 5 loop (it already uses the feature's refs); reopened units' briefs say
      `CHANGE: <slug>`.
   6. Verify as `/bull:verify` except: journey-test-writer `MODE: feature <slug>` (new journeys
      added, changed ones updated); `bull gates --journeys` runs every journey; reviewer `SCOPE:
      feature <slug>`. On acceptance: `bull status checkpoint accepted`, `bull feature accept`,
      add the feature to the memo's "Features" section, commit, `bull gates --all` on the feature
      branch, `git switch <trunk>`, `git merge --no-ff feature/<slug>/main`, `git tag
      feature/<slug>/accepted`.
- **Stopping**: the usual points (PAUSE, blocked unit, an unlisted contract change, code not in the
  spec); suggest a fresh session at each checkpoint and at the end (`/bull:feature` or
  `/bull:resume` continues). After acceptance, name the next queued feature and ask whether to start.
- **Abandon** only when the human says so: commit on the feature branch, `git switch <trunk>`, `bull
  feature abandon`, commit. The trunk is untouched, the branch stays, ideas queued on the branch are
  carried over.

### commands/adopt.md
`description: Adopt an existing app — bring an app built outside bull under it, stage by stage, until
every part is a tested module`; `argument-hint: "[nothing; continues an adoption in progress]"`.
Intro as v1 (rebuilt module by module behind its own journey tests until nothing legacy is left;
then an ordinary app, new work through `/bull:feature`; one-part apps only). Usage-check before
every step, commit after every step; refs from `bull status ref` (`adopt/…`); keep everything in
files (`docs/discussion-notes.md`, `docs/adopt/`, the memo).
- **0. Where are we?** `bull status next`. Adoption active → continue at its stage (switch branch
  first if told). App already built by bull (stage above 0, or `app-accepted`) → not for it; stop.
  Not started → stage 1. (The human may already have run `bull init --adopt`, which detects,
  applies the stack and starts the adoption; then stage 1 starts at step 4.)
- **1. Detect and discuss.** (1) `bull stack detect`; go through `block` issues (can't adopt yet;
  explain; stop), git `fix` issues (the human runs the commands you give), project `fix` issues
  (fixed in setup), `note`s that matter. (2) Confirm the detected stack and settings, `bull stack
  detect --apply [<stack>]`, commit `chore: adopt: detected project settings`. (3) `bull adopt
  start` (it commits and switches to `adopt/main`; everything else happens there). (4) `mkdir -p
  docs/adopt && bull stack detect > docs/adopt/detection.md`, commit. (5) Discuss the app as it
  exists (v1's list: purpose and users; journeys as they work today with failure paths; constraints,
  including why the app uses the UI technology it does; fragile areas and known bugs; planned
  features queued now with `bull feature add`; out of scope); notes in `docs/discussion-notes.md`.
  (6) `bull status stage 2`.
- **2. Survey and memo.** (1) The inventory: see §5 question 1. (2) Plan surveyor passes —
  `screens`, `data`, `services`, `tests`, one `module <Name>` per candidate area; ~15 files or
  3,000 lines a pass, split larger; gauge `bull status plan survey <pass>…`. (3) Each pass:
  usage-check, **surveyor** (`PASS`, file list), save as `docs/adopt/survey-<pass>.md`, commit,
  tick; `partial` → follow-up pass for `NOT READ`. (4) Propose module boundaries (purpose, legacy
  files, split files named, dependencies, app shell); agree. (5) Write the memo from `bull template
  outline` and `bull stack rules outline` with the adoption lines (spec = today's behavior;
  contracts redesigned; screens name their UI technology as the stack rules say; per module `Legacy
  files:`, `Legacy tests:`, `Callers to repoint:`; `## Legacy code` with `App shell:`, `App shell
  tests:`, `Legacy folders:`, `Renames:`; `## Known issues`). (6) Readiness list ✅/❌ plus every
  inventory file assigned and every old test assigned or marked obsolete. (7) Revise to approval;
  `bull status init-modules` (adds each module's switch-over unit; check), clear the gauge, commit
  `docs: adoption outline approved`, `bull status checkpoint outline-approved`, tag.
- **Setup (adopt variant).** `bull stack check`; walk `bull stack setup --section "For an
  adoption"`, only steps still needed, one at a time; repeat check to all ✅; commit `chore: adopt
  setup`, `bull status checkpoint setup`, tag.
- **3. Baseline.** `bull status stage 3`; gauge `bull status plan baseline clean-launch identifiers
  journeys fixes old-tests hands-on`. Steps as v1: clean-launch (code-writer `ADOPT: baseline` adds
  the stack's clean-state launch option; reviewer; commit `test: adopt: clean-state launch`);
  identifiers (screen-builder `MODE: adopt-identifiers`, a few screens a brief; skip for an app
  without screens); journeys (journey-test-writer `MODE: adopt-baseline`; `bull gates --journeys`;
  missing identifier → identifiers step); fixes (a journey failing because the app is wrong: explain,
  code-writer `ADOPT: baseline` with the bug and journey test, reviewer, up to `max_attempts`; memo
  spec says the correct behavior and `Known issues` says "fixed in baseline"; one commit per fix);
  old-tests (`bull gates --all --skip-coverage`; each failing or flaky old test → ask: fix code, fix
  test (test-writer `ADOPT: baseline`), disable with reason (listed in `Known issues`), or delete);
  `bull gates --all` passes; hands-on (the human uses the app through every journey and confirms the
  memo describes it); commit, clear gauge, `bull status checkpoint baseline`, tag.
- **4. Scaffold.** `bull status stage 4`. Renames (if `Renames:`): skeleton-builder `MODE: adopt`,
  `STEP: rename`; `bull gates --all --skip-coverage`; commit `refactor: adopt: rename clashing legacy
  types`. Then `STEP: scaffold` with the whole memo and config; gates as before; `bull api <M>
  --write` each; commit `chore: adopt: scaffold`, `bull status checkpoint scaffold`, tag.
- **5. Adopt the modules.** `bull status stage 5`, the Stage 5 loop with the adoption additions; the
  usual stops plus an old test that contradicts the spec. Trunk commits since the start: at a module
  boundary the human runs `git merge <trunk>` on `adopt/main` in a terminal (the merge guard lets
  the orchestrator merge only gated branches), resolve conflicts with them, `bull gates --all`; a
  conflict in a file a module already replaced is redone as a fix in that module.
- **6. Verify.** `bull status stage 6` (normal, strict gates from here); gauge `bull status plan
  verify legacy-check final-switch <journey>… app-review fixes hands-on backlog`. legacy-check
  (`bull adopt legacy` must print "Nothing left to replace."; each item back to its module's
  switch-over unit, or into the memo's app shell if the human agrees); final-switch (`bull stack
  setup --section "Final switch"`, then `bull stack check`, `bull gates --all`; module errors to the
  unit; app-shell errors to code-writer `ADOPT: baseline`); journeys (`bull gates --journeys`);
  app-review, fixes, hands-on as `/bull:verify` 1 and 3–5; clean the memo (remove `Legacy files:`,
  `Legacy tests:`, `Callers to repoint:`, `## Legacy code`; keep `## Known issues` only for open
  items; decisions-log line); on acceptance `bull adopt finish` (it commits `chore: adoption
  finished`), `bull gates --all` on `adopt/main`, `git switch <trunk>`, `git merge --no-ff
  adopt/main`, `git tag adopted`, clear the gauge; backlog (`bull feature list`, which goes first;
  `/bull:feature` builds them, ideally in a fresh session).
- **Abandoning** only when the human says so: commit on `adopt/main`, `git switch <trunk>`, `bull
  adopt abandon` (commits; trunk untouched; `adopt/*` branches kept; queued features carried over).

### commands/resume.md
`description: Resume the pipeline after a pause or in a fresh session`. v1's five steps: `bull
status` and `git log --oneline -15`, read the memo's build order (trust these over memory);
`bull status usage-check` (PAUSE → say when usage resets, stop); uncommitted changes → `git stash
push -m "interrupted step"`, tell the human, restart that step; `bull status resume`; continue from
`bull status next` with that stage's command (feature active → `/bull:feature`'s stage on its
branch; adoption active → `/bull:adopt`'s on `adopt/main`). New: if `next` reports a contract
approval wait, take it to the human first (golden rule 5). In a stack repo (`bull status` shows a
stack), continue with `/bull:stack`.

### commands/status.md
`description: Show pipeline progress and plan usage`. `bull status` and `bull status usage-check`;
report in a few lines: stage, modules done/total, current or next step, anything blocked or waiting
for approval, plan usage; a line each for an active feature, an adoption, a backlog (`bull feature
list`). In a stack repo: its stage, checkpoints and next step.

### commands/stack.md
`description: Build a stack (a language or platform bull can build apps with) in its own stack repo,
stage by stage`; `argument-hint: "[nothing; continues the stack in this repo]"`. Rewritten from v1's
`new-stack` for v2's staged workflow (memo § stackflow).
- **0. Refuse outside a stack repo.** `bull status` must show a stack repo (kind stack); in an app,
  or with no `.bull/`, stop and say: a stack is built in its own folder, created with `bull init
  --stack <path>` in a terminal and opened with `bull open <path>`.
- **Rules of the workflow**: usage-check before every step; commit after every step; stage and
  checkpoints through `bull status stage|checkpoint` (they refuse out of order); `bull status next`
  names the step; tags `git tag $(bull status ref tag <checkpoint>)`; the orchestrator rules (one
  subagent at a time, briefs, asking the human) apply, with `MODE: stack` briefs and no module or
  unit lines. The **Stack files** section below is the spec every brief points at (`READ ONLY
  THESE: .bull/plugin/commands/stack.md § Stack files, DESIGN.md, …`).
- **1. Discuss** (stage 1): settle every `DESIGN.md` heading with the human — language and tools
  (version, build, test framework, running one module's tests and a single failed test, coverage
  data, lint and format), contracts (what a contract is in this language and how
  `contract_declarations` reads it), modules (how `Modules/<Module>/` with `Contracts/` maps onto the
  language's normal layout; where mocks and view files go), kind (`app`|`service`|`tool`), human
  setup, adoption support (now or later), interfaces and running (formats; `[run]` for services),
  decisions log. Write them into `DESIGN.md`. ✋ Explicit approval, then `bull status checkpoint
  design-approved`, tag.
- **2. Scaffold** (`bull status stage 2`): fill every `stack.toml` key for real (no `TODO`;
  `maturity = "experimental"`), create `readers.py`, `rules.md`, `setup.md` skeletons with the
  required headings. Commit.
- **3. Fixture and cases first** (stage 3): **test-writer** `MODE: stack` writes `fixture/` (a tiny
  one- or two-module app in this stack that passes every gate; files bull can write, no hand-made
  project files unless the language needs them) and `cases.json` with every required case id. Run
  `bull stack test . --static` until it passes (shape only: the gates are not written yet). Commit.
- **4. Gate code** (stage 4; needs a static pass at HEAD): **code-writer** `MODE: stack` writes the
  gate program the `[gates]` argv lists run, `readers.py` (`contract_declarations`,
  `test_results`, `uncovered`, `check`; optional `detect`, `inventory`, `legacy_declarations`,
  `interface_check`), and `setup.md` — in this language's own idioms. `bull stack test .` (the real
  toolchain) until every case gives its expected verdict; "not run" fails. Attempts and blocked
  questions as in Stage 5. Commit.
- **5. Review** (stage 5; needs a full test pass): **code-writer** `MODE: stack` writes `rules.md`
  (`## common`, one `## <agent>` per entry in `agents`, `## outline`) from the approved design;
  **reviewer** `SCOPE: stack` reviews the whole stack folder against this spec and the design. ✋ The
  human reviews `rules.md` (these rules shape every line agents write). `bull status checkpoint
  rules-approved`, tag.
- **6. Accept**: `bull stack test .` on a clean tree, `bull status checkpoint accepted`, tag. Tell
  the human: `bull stack install <path>` makes it selectable as `experimental`; it becomes
  `verified` after one real app is accepted with it.
- **Stack files** (the spec; a section of this command so agents can read it): the folder holds
  `stack.toml` (keys and placeholders per the memo's Data models § stack.toml, summarised:
  `[stack]` name, title, description, language, kind, maturity, `source_glob`, `test_glob`,
  `comment`, `scaffold`, `gitignore`, `agents`, `[[stack.requires]]`; `[settings.<key>]` including
  `source_dir` and `test_dir`; `[gates]` argv lists `preflight`, `setup`, `build_test`,
  `build_test_fast`, `lint`, `rerun_failed`, optional `journeys`; optional `[run]`, `[interfaces]`,
  `[commands]`; the placeholders and `BULL_*` step environment; pass = exit 0, `bull-fail: <label>`
  lines add failure labels, exit 2 from preflight aborts), `readers.py` (functions above, may
  import siblings and bull's stacks contracts), `rules.md`, `setup.md` (steps, `## For a feature`,
  and with `detect` `## For an adoption` and `## Final switch`), `DESIGN.md`, `cases.json` (format,
  `layout`, `settings`, `cases` with `id`, `change` add/replace/delete, `run`, `expect` verdict,
  gate, output, recorded, ran; the required ids `clean`, `fast`, `no-tests`, `failing-test` (with
  `then`), `build-warning`, `lint`, `contract-change`, `uncovered`, `exemption`, `setup-broken`,
  plus `journey`/`journey-failing` with journeys, `interface-drift` with interfaces,
  `run-lifecycle` with `[run]`, `adopt-mode` with `detect`), `fixture/`. The required agents in
  `agents`: skeleton-builder, test-writer, code-writer, reviewer, coverage-analyst; plus
  journey-test-writer with journeys, surveyor with `detect`. The text names no language.

## 4. Agents

Every agent: a `## Stack rules` section first — "Run `bull stack rules <agent>` (add `--part
<part>` when your brief has a `PART:` line) and follow it; where it is more specific than this
file, it wins." (In `MODE: stack` briefs there are no stack rules yet: read `DESIGN.md` and the
Stack files section instead; only test-writer, code-writer and reviewer get that mode.) Every
`QUESTION:` block keeps v1's four lines and the note "the human sees none of your files, so make it
stand alone".

### agents/skeleton-builder.md
`description: Stage 3. Builds the compiling skeleton from the memo — module folders, contracts,
stubs, mocks. Also a feature's skeleton (MODE: feature) and an adoption's scaffold (MODE: adopt).`
`tools: Read, Write, Edit, Grep, Glob, Bash`. v1's content in v2 terms: layout from `.bull/config.toml`
(and the part file): `<source_dir>/Modules/<Module>/` with `Contracts/` (snapshotted by `bull
api`), the mocks and view files where the stack rules put them, implementation files from the memo;
`<test_dir>/<Module>/` one test file per implementation file. Boundaries by convention. Build steps
1–7 (folders; data models in the foundational module's `Contracts/`; protocols exactly as drafted;
stubs failing loudly "Not implemented: <Type>.<method>" in the memo's file; mocks named as the stack
rules say, realistic data, recording calls; one placeholder test per implementation file; project
settings belong to setup → `MANUAL STEPS FOR HUMAN`; check `bull gates --all --skip-coverage`).
Interface files the memo names under `## Interfaces`: create them only if the memo says the
skeleton writes them. Feature mode, Adopt mode (`STEP: rename` / `STEP: scaffold`, composition-root
file named in `## Legacy code`, never change legacy code beyond renames) and Rules as v1. Report as
v1 (`STATUS: done | blocked`, `FILES`, `MANUAL STEPS FOR HUMAN`, `QUESTION`, `NOTES`).

### agents/screen-builder.md
`description: Stage 4. Builds or revises one screen and its view model against protocol mocks. Use
for prototype screens and UI feedback.` `tools: Read, Write, Edit, Grep, Glob, Bash`. v1's content:
view where the stack rules put view files, view model with the module's other files, protocols only;
previews use the mocks; navigation as the memo; accessibility and test identifiers per stack rules.
Adopt mode `MODE: adopt-identifiers` (identifiers only; check `bull gates --all --skip-coverage`).
Rules and report as v1.

### agents/test-writer.md
`description: Stage 5. Writes unit tests for the files of one work unit from the memo's spec,
before or without seeing the implementation.` `tools: Read, Write, Edit, Grep, Glob, Bash`. v1's
content in v2 terms (inputs: only the brief's files, never the implementation; one test file per
source file in `<test_dir>/<Module>/`; one test per spec behavior incl. every error case and
boundary; mocks or in-memory fakes; unique temporary folder per test; names by behavior; replace
the placeholder; compile against the contract; ambiguous spec → `blocked`; coverage-triage briefs →
exactly those behaviors). **Reference tests** (new): a `MODE: reference`-sourced brief names
behaviors the scan found missing, in the spec's terms; write them from the spec. Never open the
reference folder (bull blocks it). **Before you report** (new, from the 2026-11-10 decision): run the
stack's formatter and lint on the test files you wrote or changed (the stack rules name the
commands) and fix what they find, so a formatting slip never costs a gate attempt. Changing an
existing unit (`CHANGE: <slug>`), Adopting (`ADOPT: legacy cases`, `ADOPT: switch-over` then `bull
gates <M> --fast`, `ADOPT: baseline`), Running short of room, and the report as v1. `MODE: stack`:
writes the stack's `fixture/` and `cases.json` from `DESIGN.md` and the Stack files section, then
`bull stack test . --static`.

### agents/code-writer.md
`description: Stage 5. Implements the source files of one work unit so their existing tests pass.
Cannot edit tests.` `tools: Read, Write, Edit, Grep, Glob, Bash`. v1's content with §1.4 wording
(Write rules; contracts off limits; other modules only through `Contracts/` and only listed ones;
document contract declarations and tricky logic; `CHANGE: <slug>`; the three `ADOPT:` modes;
check with `bull gates <M> --fast`, `bull gates --failed` while iterating but finish with `--fast`;
partial; cannot edit test files — bull blocks it — so a wrong test → `blocked`; a needed contract
change → `blocked`; report as v1). Never open the reference folder. `MODE: stack`: writes the gate
program, `readers.py`, `setup.md` (stage 4) or `rules.md` (stage 5) in the stack's language idioms
from `DESIGN.md` and the Stack files section; checks with `bull stack test .`.

### agents/reviewer.md
`description: Stage 5 and 6. Read-only targeted review of one work unit's files, one category, the
whole app, a feature, a switch-over or a stack. Also confirms coverage exemptions.` `tools: Read,
Grep, Glob, Bash`. v1's content: never modify files; scope and categories; the five categories with
§1.4 wording (security: "secrets only in the platform's secure storage"; HTTPS only; concurrency:
"UI work where the stack rules say"); `SCOPE: whole app` (consistency plus the stack rules'
whole-app items), `SCOPE: feature <slug>` (`git diff <trunk>...HEAD`, trunk from `bull status ref
trunk`), `CHANGE: <slug>` units, `SCOPE: switch-over <M>`, legacy types in module code are a
blocker during an adoption, coverage exemptions and file markers; severity; report as v1. New:
**interfaces** — a module on an interface's side matches the interface file (the gate checks shape;
you check meaning). `SCOPE: stack`: the stack folder against `DESIGN.md` and the Stack files
section (every case meaningful, readers honest about "no tests ran", rules consistent with the
design, nothing that only works on the author's machine).

### agents/coverage-analyst.md
`description: Stage 5. Explains why each uncovered block of a module is uncovered and classifies it
as missed, exempt or not-in-spec.` `tools: Read, Grep, Glob, Bash, Edit`. v1's content unchanged
except commands and §1.4 (marker syntax "as the stack rules show": `<comment> coverage-exempt:
<reason>`, `coverage-exempt-begin: <reason>` … `coverage-exempt-end`, `coverage-exempt-file:
<reason>` within the first 10 lines).

### agents/journey-test-writer.md
`description: Stage 6. Writes one end-to-end journey test per user journey in the memo and runs
them.` `tools: Read, Write, Edit, Grep, Glob, Bash`. v1's ui-test-writer in neutral terms: one test
per journey named after it, placed where the stack rules say; follow the steps literally (for an app
with screens: launch, tap, type, navigate; for a tool: run its commands; for a service: call it), then
assert the end state; failure paths as separate tests; find screen elements by test identifiers
(missing → `blocked` naming the screen); start from a clean state as the stack rules say (can't →
`blocked`); journeys that cross parts get the running parts' addresses from bull (the stack rules
say how). Feature mode, Adopt mode (`MODE: adopt-baseline`, report app misbehaviour as `fail`). Run
`bull gates --journeys`; report each journey pass/fail. Report as v1.

### agents/surveyor.md
`description: Adoption stage 2. Read-only survey of an existing app's code, one bounded pass at a
time (screens, data, services, a candidate module, or tests), so the orchestrator can write the
memo.` `tools: Read, Grep, Glob, Bash`. v1's content (passes, rules, report) in v2 terms; the
inventory input per §5 question 1.

### agents/legacy-test-scanner.md
`description: Stage 5. Compares a module's old tests (an adoption's legacy tests, or a rewrite's
reference tests) with its new spec-based tests and lists the cases the new ones miss.` `tools: Read,
Grep, Glob`. v1's content (never modify files, never open implementation files; covered / missed /
contradicts / not-in-spec / obsolete; behavior, not names: `old-tool status` and `bull status` are
the same behavior), with two modes: `MODE: adopt` (old tests = the memo's `Legacy tests:`) and
`MODE: reference` (old tests = the memo's `Reference tests:` entries, inside the reference folder;
you are the only agent that reads it). Report as v1, plus a final `COUNTS: covered n, missed n,
contradicts n, not-in-spec n` line (the orchestrator records it with `bull status refscan`).

## 5. For the human

### Choices this note makes (approving the note approves them)
1. `/bull:stack` runs the stack workflow with test-writer, code-writer and reviewer in `MODE: stack`
   (the brief's "stacks built like apps"); the spec they read is a **Stack files** section inside
   `commands/stack.md`, since a stack repo has no other copy of it. No module outside plugin_text
   changes.
2. legacy-test-scanner serves both adoption (`MODE: adopt`) and reference tests (`MODE: reference`)
   and ends its report with a `COUNTS:` line for `bull status refscan`.
3. `/bull:prototype` gets a "no screens" path (record the skip, checkpoint `ui-approved`), as this
   app did by decision.
4. `/bull:verify`'s "device test" becomes "hands-on" (use the app the way its users will).
5. `/bull:feature` stage 6 records `bull status checkpoint accepted` before `bull feature accept`
   (the features spec refuses accept without it).
6. Agents keep `tools:` lines in Claude Code's tool names (the memo requires `tools`); v1's
   `disallowedTools: Agent` becomes an explicit list without the agent tool.

### Open question
1. **No inventory command.** v1's adoption survey starts from `ios-pipeline stack inventory` (every
   legacy file with size, declared and used types). v2's memo has an optional `inventory` stack
   reader but no `bull` command calls it, and the text rules forbid naming a command that isn't in
   the Commands table. Options: (a) **recommended** — `/bull:adopt` plans its passes from `bull
   adopt legacy` (before the memo exists it lists every legacy source and test file) plus `wc -l`,
   and surveyors find types themselves; no code change, the stacks' `inventory` reader stays unused
   until a later feature; (b) add `bull stack inventory` to the Commands table and to the
   `adoption` module (reopens a done module, a contract-free cli change); (c) leave the inventory
   out and let the surveyor's `module` passes discover files. This note is written for (a): §3
   adopt step 2.1 = `bull adopt legacy > docs/adopt/inventory.md`, commit.
