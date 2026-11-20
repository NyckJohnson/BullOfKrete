# GUI

## Idea

A local GUI across all registered apps: the real coding-agent session in a terminal, each app's
progress at a glance, and doc review where feedback becomes change sets the orchestrator applies.
No approvals in the GUI. Design: `docs/gui.md` (agreed 2026-10-24/27 for v1; restate in bull terms).
It settles the memo's open question as a local web app (Python backend, plain HTML/JS, 127.0.0.1,
token and Origin checks, tmux-backed sessions, xterm.js). Prerequisites from gui.md not yet in bull:
an app registry (`bull apps`), a general "waiting for the human" state (today `status wait` covers
contract changes only), context use in `usage.json`, and the pending-edits queue with its
step-boundary check. gui.md plans six PRs; discuss may split this into several features. Open: how
the GUI itself is built (see "Stack for the GUI").

## Discussion notes

## Agreed scope
