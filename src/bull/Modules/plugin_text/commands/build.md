---
description: "Stage 5 — build modules one at a time, foundational first"
argument-hint: "[module name to build only that one]"
---

# Stage 5: Modules

You build the app module by module, in the memo's build order, foundational modules first. Each
module goes through the orchestrator's **Stage 5 loop**: tests, code, gates and review per unit,
then the reference-test scan, coverage triage, the full gates, the merge, the contract snapshot and
the tag.

1. Run `bull status usage-check`. If it reports `PAUSE`, follow the orchestrator's rule for a pause
   and stop.
2. Run `bull status stage 5`. If it is refused, tell the human which earlier step is missing and
   stop. During a feature, this sets the feature's stage, not the app's, and every branch and tag
   comes from `bull status ref` (prefixed `feature/<slug>/`); during an adoption they are prefixed
   `adopt/`. Always take branch and tag names from `bull status ref`, never write them by hand.
3. Pick the module. If `$ARGUMENTS` names a module, build only that one (its dependencies must all
   be `done`). Otherwise run `bull status next`: it names the next module and the step within it.
4. Follow the **Stage 5 loop** in the orchestrator instructions exactly, for this module and then
   for each next module `bull status next` names. Run `bull status usage-check` before every step
   of the loop.
   - Use `bull gates <M> --fast` while iterating on a unit. While fixing failures,
     `bull gates --failed` reruns only the tests that failed in the last run; finish with `--fast`.
   - Only the full `bull gates <M>` (without `--fast`) records the pass the merge guard needs, and
     only on a clean tree.
   - After each merge, run `bull gates --after-merge <branch>` on the base branch.
5. **Adoption.** During an adoption, unit briefs carry the `ADOPT:` lines the orchestrator's
   **Adopting an existing app** section gives (`ADOPT: unit` with the `LEGACY FILES`), and each
   module's last unit is its switch-over (`bull status next` names it). Run the switch-over as that
   section describes.
6. After the last module, run `bull gates --all` on the base branch: the complete run, every test.
   Failures go to the owning module's unit, through its Stage 5 loop.
7. Stop and report to the human when:
   - **All modules are done** (and `bull gates --all` passed): tell the human that the modules are
     built and that the next step is to run `/bull:verify`. During a feature or an adoption,
     continue instead with its stage 6, as `/bull:feature` or `/bull:adopt` says.
   - **Usage-check reports `PAUSE`**: commit, run `bull status pause "<reason>"`, tell the human
     when usage resets, and stop.
   - **A decision needs the human**: a blocked unit (the attempt cap reached, or a subagent returned
     `blocked`), a contract change, or a reference-scan or coverage finding that needs the human
     (`contradicts`, `not-in-spec`). Ask, following **Asking the human**, and wait for the answer.
8. Report to the human only at module boundaries: one short line per module (merged and tagged, or
   where it stopped). Don't narrate each unit.

When `$ARGUMENTS` named a single module, stop after that module's tag and report.
