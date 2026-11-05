---
description: Adopt an existing app — bring an app built outside the pipeline under it, stage by stage, until every part is a tested module
argument-hint: "[nothing; continues an adoption in progress]"
---

Adopting brings an app that was built without the pipeline under it. Its code is rebuilt module by
module, behind its own journey tests, until nothing legacy is left; then it is an ordinary pipeline
app and new work goes through `/feature`. Follow the **Adopting an existing app** section of the
orchestrator instructions; `docs/adopt.md` in the pipeline has the design. Adoption works on an app
with one part (`status adopt start` refuses more).

Run `ios-pipeline status usage-check` before every step, as always, and commit after every completed
step. Checkpoints, tags and branches come from `ios-pipeline status ref` (`adopt/…` while adopting).
Tag with `git tag $(ios-pipeline status ref tag <name>)`. Keep everything the stages produce in files
(`docs/discussion-notes.md`, `docs/adopt/`, the memo): nothing may live only in this conversation.

## 0. Where are we?

Run `ios-pipeline status next`.
- **An adoption is active**: continue at its stage below. If `next` says to switch branch, do that first.
- **The app is a pipeline app already** (stage above 0, or `app-accepted`): `/adopt` isn't for it; say
  so and stop.
- **Not started**: begin with stage 1.

## 1. Detect and discuss

1. `ios-pipeline stack detect`. Go through the report with the human:
   - **⛔ blocking**: the pipeline can't adopt this app yet (e.g. an unsupported dependency manager or language, or git submodules).
     Explain each in plain words and that supporting it needs a pipeline upgrade; stop here.
   - **Git 🔧** (not on the trunk, uncommitted changes, clashing branch or tag names, nested repos):
     these must be fixed before the adoption starts. Tell the human the exact commands; they run them.
   - **Project 🔧**: fixed in the adoption's setup step; just list them.
   - **ℹ️ notes**: mention the ones that matter (language version, UI technology, other targets, git hooks).
2. Confirm the stack detection ranked first and its settings (project, folders, targets, trunk branch)
   with the human, then `ios-pipeline stack detect --apply` (it selects that stack; name another with
   `--apply <stack>`) and commit `chore: adopt: detected project settings`.
3. `ios-pipeline status adopt start`, commit `chore: start adoption`, then `git switch -c adopt/main`.
   Everything from here on happens on `adopt/main`; the trunk stays as it is until the end.
4. Save the report: `mkdir -p docs/adopt && ios-pipeline stack detect > docs/adopt/detection.md`, commit.
5. Discuss the app as `/discuss` does, but about the app as it exists (the stack is already chosen):
   - purpose and users;
   - the core user journeys **as they work today**, with failure paths (the survey checks them against
     the code);
   - constraints: minimum platform version (and why the app uses the UI technology it does), offline, accounts, sync, services;
   - fragile areas and bugs the human knows about;
   - **planned features**: queue each one now with `ios-pipeline status feature add "<Title>: <what>"`;
     they are built after the adoption;
   - out of scope.
   Keep the notes in `docs/discussion-notes.md` and commit as you go.
6. When it's all agreed: `ios-pipeline status stage 2`.

## 2. Survey and memo

1. `ios-pipeline stack inventory > docs/adopt/inventory.md`, commit. It lists every legacy file with its
   size, the types it declares and the app types it uses, plus the old tests.
2. Plan the surveyor passes from the inventory: `screens`, `data`, `services`, `tests`, and one
   `module <Name>` pass per candidate area. Keep each pass to a list a subagent can read properly
   (about 15 files or 3,000 lines); split larger ones. Start the gauge:
   `ios-pipeline status plan survey <one item per pass>`.
3. For each pass: `usage-check`, delegate to **surveyor** (`PASS`, the file list, their inventory lines),
   save its report as `docs/adopt/survey-<pass>.md`, commit, `tick`. A `partial` report gets a follow-up
   pass for its `NOT READ` files.
4. Propose the module boundaries to the human before writing the memo: each module's purpose, the legacy
   files it takes over (split files named), its dependencies, and the app shell. Agree them.
5. Write `docs/outline.md` from the template (`ios-pipeline template outline`) and the stack's memo rules
   (`ios-pipeline stack rules outline`), including the **adoption lines**:
   - the **behavior spec describes what the app does today**, from the survey;
   - **contracts are redesigned** to the pipeline's standards while keeping that behavior;
   - every screen names its UI technology, as the stack's memo rules say (adopted screens keep theirs,
     with their logic in a tested view model);
   - each module has `Legacy files:`, `Legacy tests:` and `Callers to repoint:`;
   - `## Legacy code` lists the app shell (what belongs there: the stack's memo rules), the legacy folders and the `Renames:` (legacy types whose
     names a contract takes);
   - `## Known issues` lists what the survey's suspected issues turned out to be.
6. Report the `/outline` readiness list as ✅/❌, plus: **every file in the inventory is assigned** to a
   module or the app shell, and every old test to a module (or marked obsolete).
7. Revise with the human until they approve. Then `ios-pipeline status init-modules` (each module gets
   a final switch-over unit; check the output), `ios-pipeline status plan survey --clear`, commit
   `docs: adoption outline approved`, `ios-pipeline status checkpoint outline-approved`, tag.

## Setup (adopt variant)

1. `ios-pipeline stack check`. Walk the human through the **For an adoption** section of
   `ios-pipeline stack setup`, only the steps still needed, one at a time, waiting for "done".
2. Repeat `ios-pipeline stack check` until every item is ✅.
3. Commit `chore: adopt setup` (the project changes), `ios-pipeline status checkpoint setup`, tag.

## 3. Baseline

`ios-pipeline status stage 3`. Gauge: `ios-pipeline status plan baseline clean-launch identifiers journeys fixes old-tests device-check`.

1. **clean-launch**: **code-writer** with `ADOPT: baseline`: add support for the stack's clean-state
   launch option (the stack rules name it; UI tests use it to start from empty, in-memory state) to the
   app's startup and persistence. Then **reviewer** on that change. Commit `test: adopt: clean-state launch`.
2. **identifiers**: **screen-builder** with `MODE: adopt-identifiers`, a few screens per brief, naming the
   elements the journeys touch. Commit.
3. **journeys**: **ui-test-writer** with `MODE: adopt-baseline`: one test per memo journey. Run
   `ios-pipeline gates --app-ui-tests`. A missing identifier goes back to step 2.
4. **fixes**: a journey that fails because the **app** is wrong is a bug: explain it to the human, then
   **code-writer** (`ADOPT: baseline`, the bug, the journey test) fixes it, reviewer checks it (up to 3
   attempts). Update the memo: the spec now says the correct behavior, and `Known issues` says "fixed in
   baseline". Commit each fix on its own.
5. **old-tests**: `ios-pipeline gates --all --skip-coverage`. For each old test that fails or flickers,
   ask the human: fix the code (code-writer, `ADOPT: baseline`), fix the test (test-writer), disable it
   (test-writer marks it disabled with the reason; list it in `Known issues`), or delete it.
6. `ios-pipeline gates --all` must pass: the build, the old tests and the journey tests.
7. **device-check**: the human installs the app on a device, walks through every journey and confirms
   the memo describes the app. Differences are memo fixes or bugs (step 4).
8. Commit, `ios-pipeline status plan baseline --clear`, `ios-pipeline status checkpoint baseline`, tag.
   This is the adoption's second checkpoint: from here the journey tests guard every change.

## 4. Scaffold

`ios-pipeline status stage 4`.

1. If the memo lists `Renames:`, **skeleton-builder** with `MODE: adopt`, `STEP: rename` and the list.
   `ios-pipeline gates --all --skip-coverage`, commit `refactor: adopt: rename clashing legacy types`.
2. **skeleton-builder** with `MODE: adopt`, `STEP: scaffold`, the whole memo and the config.
3. `ios-pipeline gates --all --skip-coverage`; `ios-pipeline api <Module> --write` for each module.
4. Commit `chore: adopt: scaffold`, `ios-pipeline status checkpoint scaffold`, tag.

## 5. Adopt the modules

`ios-pipeline status stage 5`, then the **Stage 5 loop** for every module in build order, with the
adoption additions in the orchestrator instructions (`/build` runs the same loop). Stop at the usual
points: PAUSE, a blocked unit, a contract change, code that isn't in the spec, an old test that
contradicts the spec.

If the human has committed to the trunk since the adoption started, bring those commits in at a
module boundary: ask the human to run `git merge <trunk>` on `adopt/main` in a terminal (the merge guard
only lets the orchestrator merge gated branches), resolve conflicts with them, then run
`ios-pipeline gates --all`. A conflict in a file that a module already replaced means the change must
be redone in the module: treat it as a fix for that module.

## 6. Verify

`ios-pipeline status stage 6`. From this stage the gates are the normal, strict ones.
Gauge: `ios-pipeline status plan verify legacy-check final-switch <one item per journey> app-review fixes device-test backlog`.

1. **legacy-check**: `ios-pipeline status adopt legacy` must say `legacy: empty`. Each item left goes
   back to the module that should own it (reopen its switch-over unit), or into the memo's app shell if
   the human agrees it belongs there.
2. **final-switch**: walk the human through the **Final switch** section of `ios-pipeline stack setup`
   (the project moves to the stack's full strictness, e.g. a newer language mode); then
   `ios-pipeline stack check` and `ios-pipeline gates --all`. Errors in a module go to its unit; errors in
   the app shell go to **code-writer** with `ADOPT: baseline` and the files.
3. **journeys**: `ios-pipeline gates --app-ui-tests`; every journey passes.
4. **app-review**, **fixes**, **device-test**: as `/verify` steps 1 and 3-5 (whole-app review, routing
   findings to the owning module, the human's device test with feedback sorted into fix now, later
   (queued as features) or drop).
5. Clean the memo: remove the adoption-only lines (`Legacy files:`, `Legacy tests:`,
   `Callers to repoint:`, the `## Legacy code` section) and keep `## Known issues` only for what is still
   open. Add a decisions-log line for the adoption.
6. When the human accepts: `ios-pipeline status adopt finish`, commit `chore: adoption finished`,
   `ios-pipeline gates --all` on `adopt/main`, then `git switch <trunk>` (`ios-pipeline status ref trunk`),
   `git merge --no-ff adopt/main`, `git tag adopted`, `ios-pipeline status plan verify --clear`.
7. **backlog**: show `ios-pipeline status feature list` (the features queued during the discussion and
   the device test) and ask which goes first; `/feature` builds them, ideally in a fresh session.

## Abandoning

Only when the human says so: commit on `adopt/main`, `git switch <trunk>`,
`ios-pipeline status adopt abandon`, commit. The trunk is untouched; `adopt/*` branches stay for
reference; queued features are carried over.
