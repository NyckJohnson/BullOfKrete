# Clear and resume in one command

## Idea

A single command that does `/clear` and then `/bull:resume`, so starting a fresh session at a
handoff point is one step. The lightweight forerunner of "Automatic orchestrator restarts".
Open: whether a plugin command can clear the conversation itself, or this needs bull to restart the
session from outside.

## Discussion notes

- 2026-11-20: settled the open question. A plugin command cannot clear its own conversation: commands
  only hand the model instructions, and `/clear` is a built-in only the human can type. Inside a
  session the best possible is `/clear` then `/bull:resume` (works today), or an auto-resume after
  `/clear` that still needs one message from the human. From outside, `claude "/bull:resume"` starts
  a fresh session that resumes at once.
- Moved after GUI: the GUI's tmux-backed session can type `/clear` and `/bull:resume` into the real
  session itself, so a GUI button delivers the one-step version. Scope this feature as that button
  (see gui.md), plus any CLI/handoff-message help still worth having.

## Agreed scope
