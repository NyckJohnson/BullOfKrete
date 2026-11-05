---
description: Resume the pipeline after a pause or in a fresh session
---

1. Run `ios-pipeline status summary` and `git log --oneline -15`, and
   read the memo's build order. That is your full picture; trust it over memory.
2. Run `ios-pipeline status usage-check`. If PAUSE, tell the human when
   usage resets and stop.
3. If there are uncommitted changes, they belong to an unfinished step. Run
   `git stash push -m "interrupted step"` and tell the human; restart that step.
4. Run `ios-pipeline status unpause`.
5. Continue the current stage from `ios-pipeline status next`, using
   that stage's command instructions. If a feature is active (the summary shows `Feature:`),
   follow `/feature`'s instructions for its stage, on its branch. If an adoption is active (the
   summary shows `Adoption:`), follow `/adopt`'s instructions for its stage, on `adopt/main`.
