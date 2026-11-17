---
description: "Adopt an existing app — bring an app built outside bull under it, stage by stage, until every part is a tested module"
argument-hint: "[nothing; continues an adoption in progress]"
---

# Adopt an existing app

An app built outside bull is brought under it here. You rebuild it module by module, each one behind
journey tests written against the app as it works today, until nothing legacy is left. Then it is an
ordinary accepted app, and new work comes in through `/bull:feature`. Adoption is for one-part apps
only. The orchestrator's **Adopting an existing app** section gives the rules; this command gives
the steps.

Rules for every step:

- Run `bull status usage-check` before every step. On `PAUSE`, follow the orchestrator's rule for a
  pause and stop.
- Commit after every step. Run each `bull status …` change before that step's commit, and tag after
  the commit.
- `bull status stage <n>` refuses when a checkpoint is missing. Tell the human which one: stage 3
  needs `outline-approved` and `setup`, stage 4 `baseline`, stage 5 `scaffold`.
- Take every branch and tag name from `bull status ref`: during an adoption they are prefixed
  `adopt/`. Tag a checkpoint with `git tag $(bull status ref tag <checkpoint>)`.
- Keep everything in files: the discussion in `docs/discussion-notes.md`, the detection report and
  the survey in `docs/adopt/`, the decisions in the memo. Nothing important may live only in this
  conversation.

## 0. Where are we?

1. Run `bull status next`.
2. Decide from what it says:
   - **An adoption is active**: continue at its stage below. If `next` says to switch branch, switch
     branch first.
   - **The app was already built by bull** (its stage is above 0, or it has the `app-accepted`
     checkpoint): this command is not for it. Tell the human so; new work goes through
     `/bull:feature`. Stop.
   - **Not started**: go to stage 1. If the human already ran `bull init --adopt` in a terminal, it
     has detected the stack, applied it and started the adoption; start stage 1 at its step 4.

## 1. Detect and discuss

1. Run `bull stack detect` and go through its report with the human:
   - **`block` issues**: the app can't be adopted yet. Explain each one and its fix, and stop.
   - **git `fix` issues** (nested repositories, clashing branches or tags, uncommitted changes): give
     the human the commands to run in a terminal, and run `bull stack detect` again afterwards.
   - **project `fix` issues**: these are fixed during setup; note them.
   - **`note`s**: mention the ones that matter.
2. Confirm the detected stack and its settings with the human. Run
   `bull stack detect --apply [<stack>]` (name a stack only if the human picks a different one), then
   commit `chore: adopt: detected project settings`.
3. Run `bull adopt start`. It commits by itself and switches to `adopt/main`; everything else
   happens on that branch.
4. Save the detection report:
   `mkdir -p docs/adopt && bull stack detect > docs/adopt/detection.md`, then commit.
5. Discuss the app as it exists today with the human, and keep notes in `docs/discussion-notes.md`:
   - its purpose and its users;
   - the user journeys as they work today, each with its failure paths;
   - constraints, including why the app uses the UI technology it does;
   - fragile areas and known bugs;
   - planned features: queue each one now with `bull feature add "<Title>: <desc>"`;
   - what is out of scope.

   Commit the notes as you go.
6. Run `bull status stage 2`, then commit.

## 2. Survey and memo

1. **Inventory.** Run `bull adopt legacy > docs/adopt/inventory.md`. Before the memo exists it lists
   every legacy source and test file. Add each file's size with `wc -l`. Commit.
2. **Plan the surveyor passes.** Plan one pass each for `screens`, `data`, `services` and `tests`,
   and one `module <Name>` pass per candidate area of the app. Keep a pass to about 15 files or
   3,000 lines; split anything larger into several passes. Set the gauge with
   `bull status plan survey <pass>…` and mirror it as a task list.
3. **Run each pass.** For each pass: run `bull status usage-check`, brief the **surveyor** with the
   `PASS` and its file list, save its report as `docs/adopt/survey-<pass>.md`, tick the pass with
   `bull status tick <pass>`, and commit. If the surveyor returns `partial`, plan a follow-up pass for
   the files under its `NOT READ`.
4. **Propose module boundaries.** From the survey, propose the modules: each one's purpose, its legacy
   files (name any file that must be split between modules), its dependencies, and what stays in the
   app shell. Agree on them with the human.
5. **Write the memo.** Start from `bull template outline` and follow `bull stack rules outline`, with
   these adoption lines:
   - The behavior spec describes today's behavior; contracts are redesigned.
   - Screens name their UI technology, as the stack rules say.
   - Each module has `Legacy files:`, `Legacy tests:` and `Callers to repoint:` lines.
   - A `## Legacy code` section holds `App shell:`, `App shell tests:`, `Legacy folders:` and
     `Renames:`.
   - A `## Known issues` section lists the bugs and fragile areas found.
6. **Readiness list.** Show the human the readiness list with ✅ or ❌ per item, as `/bull:outline`
   does, plus two adoption items: every file in the inventory is assigned to a module or to the app
   shell, and every old test is assigned to a module or marked obsolete.
7. **Approval.** Revise until the human approves the memo. Then:
   1. Run `bull status init-modules`. It adds each module's switch-over unit; check its output.
   2. Run `bull status plan survey --clear`.
   3. Run `bull status checkpoint outline-approved`.
   4. Commit `docs: adoption outline approved`.
   5. Tag with `git tag $(bull status ref tag outline-approved)`.

## Setup (the adoption variant)

1. Run `bull stack check`.
2. Walk the human through `bull stack setup --section "For an adoption"`, only the steps still
   needed, one at a time.
3. Run `bull stack check` again until every item is ✅.
4. Run `bull status checkpoint setup`.
5. Commit `chore: adopt setup`.
6. Tag with `git tag $(bull status ref tag setup)`.

## 3. Baseline

Journey tests pin the app as it works today, before any code moves.

1. Run `bull status stage 3`.
2. Set the gauge:
   `bull status plan baseline clean-launch identifiers journeys fixes old-tests hands-on`, and
   mirror it as a task list. Tick each item with `bull status tick <item>` as it finishes, before
   that step's commit.
3. **clean-launch.** Brief the **code-writer** with `ADOPT: baseline` to add the stack's clean-state
   launch option, so each journey test starts from a known state. Then the **reviewer**. Commit
   `test: adopt: clean-state launch`.
4. **identifiers.** Brief the **screen-builder** with `MODE: adopt-identifiers`, a few screens per
   brief, to add the identifiers journey tests need. Skip this step for an app without screens.
   Commit after each brief.
5. **journeys.** Brief the **journey-test-writer** with `MODE: adopt-baseline`: one journey test per
   memo journey, against the app as it is. Run `bull gates --journeys`. A test that fails for a
   missing identifier goes back to the identifiers step. Commit.
6. **fixes.** A journey test that fails because the app itself is wrong is a bug. Explain it to the
   human. If they want it fixed, brief the **code-writer** with `ADOPT: baseline`, the bug and its
   journey test; then the **reviewer**; up to `max_attempts` attempts. The memo's spec says the
   correct behavior, and its `## Known issues` entry says "fixed in baseline". One commit per fix.
7. **old-tests.** Run `bull gates --all --skip-coverage`. For each old test that fails or is flaky,
   ask the human whether to:
   - fix code (the code-writer with `ADOPT: baseline`);
   - fix test (the **test-writer** with `ADOPT: baseline`);
   - disable it with a reason (list it in `## Known issues`);
   - delete it.

   Then run `bull gates --all` until it passes. Commit.
8. **hands-on.** Ask the human to use the app the way its users will (the stack's setup guide says
   how), through every journey, and to confirm the memo describes it. Fix the memo where it doesn't.
9. Then:
   1. Run `bull status plan baseline --clear`.
   2. Run `bull status checkpoint baseline`.
   3. Commit `test: adopt: baseline`.
   4. Tag with `git tag $(bull status ref tag baseline)`.

## 4. Scaffold

1. Run `bull status stage 4`.
2. **Renames**, only if the memo's `Renames:` line lists any:
   1. Brief the **skeleton-builder** with `MODE: adopt` and `STEP: rename`.
   2. Run `bull gates --all --skip-coverage`; on a failure, retry as `/bull:skeleton` does.
   3. Commit `refactor: adopt: rename clashing legacy types`.
3. **Scaffold:**
   1. Brief the **skeleton-builder** with `MODE: adopt`, `STEP: scaffold`, the whole memo and the
      config. It writes the modules' contracts and mocks; no stubs.
   2. Run `bull gates --all --skip-coverage`; on a failure, retry as `/bull:skeleton` does.
   3. Run `bull api <M> --write` for each module.
   4. Run `bull status checkpoint scaffold`.
   5. Commit `chore: adopt: scaffold`.
   6. Tag with `git tag $(bull status ref tag scaffold)`.

## 5. Adopt the modules

1. Run `bull status stage 5`.
2. Run the Stage 5 loop as `/bull:build` does, with the adoption additions from the orchestrator's
   **Adopting an existing app** section: `ADOPT: unit` briefs with the module's `LEGACY FILES`, and
   each module's last unit is its switch-over.
3. Stop at the usual points (`PAUSE`, a blocked unit, a contract change, code not in the spec), and
   also when an old test contradicts the spec. Ask the human as **Asking the human** describes.
4. **Commits on the trunk since the adoption started.** At a module boundary, ask the human to run
   `git merge <trunk>` on `adopt/main` in a terminal (the trunk comes from `bull status ref trunk`;
   the merge guard lets you merge only gated branches). Resolve any conflicts with them, then run
   `bull gates --all`. A conflict in a file that a module has already replaced is redone as a fix in
   that module, through its Stage 5 loop.

## 6. Verify

From here the gates are the normal, strict ones.

1. Run `bull status stage 6`.
2. Set the gauge:
   `bull status plan verify legacy-check final-switch <one item per journey> app-review fixes hands-on backlog`,
   and mirror it as a task list. Tick each item with `bull status tick <item>` as it finishes, before
   that step's commit.
3. **legacy-check.** Run `bull adopt legacy`. It must print "Nothing left to replace.". Send each
   item it lists back to its module's switch-over unit, or, if the human agrees, add it to the
   memo's app shell. Commit.
4. **final-switch.** Walk the human through `bull stack setup --section "Final switch"`, then run
   `bull stack check` and `bull gates --all`. Errors in module code go to the owning unit; errors
   in the app shell go to the **code-writer** with `ADOPT: baseline`. Commit.
5. **Journey tests.** Run `bull gates --journeys`. Tick each journey as its test passes, and commit.
6. **app-review**, **fixes** and **hands-on**: run them as `/bull:verify` steps 6 to 8 describe.
   Do not run its acceptance or backlog steps; steps 8 and 9 below replace them.
7. **Clean the memo.** Remove the `Legacy files:`, `Legacy tests:`, `Callers to repoint:`,
   `Legacy folders:` and `Renames:` lines. Keep the `App shell:` and `App shell tests:` lines until
   `bull adopt finish` has succeeded: finish reads them. Keep `## Known issues` only for items still
   open. Add a decisions-log line saying the adoption is complete. Commit.
8. On the human's acceptance:
   1. Tick `hands-on`.
   2. Run `bull adopt legacy` just before finishing; it must still print "Nothing left to replace.".
   3. Run `bull adopt finish`. It is refused while `bull adopt legacy` lists anything. It records the
      end of the adoption and commits `chore: adoption finished` by itself.
   4. Remove the rest of the memo's `## Legacy code` section, with the `App shell:` and
      `App shell tests:` lines, in a follow-up commit.
   5. Run `bull gates --all` on `adopt/main`. All must pass: the merge guard needs a recorded pass
      for `adopt/main`'s head before the merge.
   6. Run `git switch <trunk>`, then `git merge --no-ff adopt/main`.
   7. Run `git tag adopted`. The tag is written out: the adoption has ended, so `bull status ref` no
      longer gives the `adopt/` prefix.
9. **backlog.** Show the queue with `bull feature list`; the features queued during the adoption go
   first. Help the human order it with `bull feature move <slug> <pos>`. Tick `backlog`, run
   `bull status plan verify --clear`, and commit. Tell the human that `/bull:feature` builds them,
   ideally in a fresh session.

## Abandoning

Abandon an adoption only when the human says so:

1. Commit any work on `adopt/main`.
2. Run `git switch <trunk>`.
3. Run `bull adopt abandon`. It commits by itself.

This leaves the trunk untouched except for that one commit. The `adopt/*` branches are kept, and
queued features from `adopt/main` are carried over to the trunk's backlog.
