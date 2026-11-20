# Context use in the status line

## Idea

The bull status line shows 5-hour and weekly usage but not the session's context-window use, which v1's status line showed. Add it (e.g. ctx 38%), read from the status-line input Claude Code passes (claude_code parse_statusline, cli statusline.py). Also record it in usage.json so the GUI header and show-subagents-context-use can read it later. Open: which status-line input fields carry context use in the installed Claude Code, and what to show when they are missing.

## Discussion notes

- 2026-11-19, the open question is answered. Claude Code's status-line docs (code.claude.com/docs/en/statusline,
  installed CLI 2.1.329) list `context_window` with `used_percentage` (0–100, input tokens only),
  `remaining_percentage`, `context_window_size`, `total_input_tokens`/`total_output_tokens` (0 before
  the first response) and `current_usage` (null before the first call and right after `/compact`).
  `used_percentage` "may be null early in the session".
- Today `parse_statusline` makes a UsageSample only when a rate-limit window has a percentage. The
  line falls back to `Usage.latest()` when the input has no sample.
- The change touches the claude_code contract (`parse_statusline`, `StatusLineInput`/`UsageSample`)
  and the usage contract (`UsageSample`, usage.json), plus the cli line (statusline.py).

## Agreed scope
