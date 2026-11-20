# Context use in the status line

## Idea

The bull status line shows 5-hour and weekly usage but not the session's context-window use, which v1's status line showed. Add it (e.g. ctx 38%), read from the status-line input Claude Code passes (claude_code parse_statusline, cli statusline.py). Also record it in usage.json so the GUI header and show-subagents-context-use can read it later. Open: which status-line input fields carry context use in the installed Claude Code, and what to show when they are missing.

## Discussion notes

## Agreed scope
