# Module tag and branch share a name

## Idea

a module's finished tag has the same name as its branch, so git picks the tag on a re-merge after a verify fix and silently merges nothing (hit 2026-11-23 in accept-tests-for-defensive-error); give tags a distinct name, refuse ambiguous merge names, or use a fresh branch for verify fixes

## Discussion notes

- 2026-11-23, findings: `Refs.tag("module/<M>")` and `Refs.module_branch(M)` give the same name
  (`<prefix>module/<M>`). git resolves an ambiguous name to the tag (rev-parse warns
  "refname is ambiguous"). The merge guard resolves the target with `git.head` too, so it saw the
  tag's old sha. That sha already had a recorded pass, so the guard allowed the merge, and
  `git merge` said "Already up to date".
- Naming lives in `status/refs.py` (generic `tag(label)`); the module tag label `module/<M>` comes
  only from the orchestrator text (orchestrator.md: the stages table and Stage 5 step 9) and
  journey 2. `status/summary.py` lists pipeline tags by the patterns `module/*`, `feature/*`,
  `adopt/*`.
- `gates --after-merge <branch>` resolves the branch name the same way.
- Proposal: (1) module tags become `done/<M>` (with the mode prefix); (2) the merge guard and
  `gates --after-merge` refuse a name that is both a branch and a tag; (3) no fresh branch for
  verify fixes. No contract change: `Refs.tag` stays generic, and `Git.branch_exists`/`Git.tags`
  already exist.

## Agreed scope

Agreed with the human 2026-11-23.

1. A finished module's tag is `done/<M>`, with the mode prefix (`feature/<slug>/done/<M>`,
   `adopt/done/<M>`), taken from `bull status ref tag done/<M>`. `bull status tags` lists `done/*`
   tags as pipeline tags. Existing `module/<M>` tags are left alone.
2. The merge guard and `bull gates --after-merge <branch>` refuse a name that is both a branch and a
   tag, naming both and suggesting `refs/heads/<name>`. Both accept `refs/heads/<name>`, and treat it
   as that branch (a module branch is still recognized).
3. Out of scope: a fresh branch for verify fixes; renaming or deleting existing tags.

Affected: status (tag listing), hooks (merge guard), gates (after-merge), plugin_text (orchestrator
text), journey 2 (tag `done/<M>`, plus a failure path for an ambiguous name). No contract changes.
