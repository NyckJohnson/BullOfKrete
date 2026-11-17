---
description: "Resume the pipeline after a pause or in a fresh session"
---

# Resume

You are picking up work that stopped: after a usage pause, or in a fresh session with no memory of
the last one. The files are the memory; rebuild your picture from them.

**A stack repo first.** Run `bull status`. If it shows a stack repo (a stack and its stage), run
`git log --oneline -15`, handle uncommitted changes as step 3 below says, run `bull status next`,
and continue with `/bull:stack`. Skip the usage check and the resume step: a stack repo has neither.

In an app, follow these steps:

1. **Read the state.** Run `bull status` and `git log --oneline -15`, and read the memo's build
   order in `docs/outline.md`. Trust these over your memory of earlier sessions or anything in this
   conversation.
2. **Check usage.** Run `bull status usage-check`. If it reports `PAUSE`, tell the human when usage
   resets and stop.
3. **Uncommitted changes.** If `git status` shows any, the step that made them was interrupted. Run
   `git stash push -m "interrupted step"`, tell the human what you stashed, and restart that step
   from its beginning.
4. **Clear the pause.** Run `bull status resume`.
5. **Continue.** Run `bull status next` and continue with that stage's command:
   - **A feature is active**: continue with `/bull:feature`, at the feature's stage, on its branch
     (switch branch first if `next` says so).
   - **An adoption is active**: continue with `/bull:adopt`, at the adoption's stage, on `adopt/main`.
   - **Otherwise**: the stage's own command (`/bull:build` for stage 5, and so on).

   If `next` reports a contract change waiting for approval, take it to the human first, as golden
   rule 5 and **Asking the human** describe, before anything else.
