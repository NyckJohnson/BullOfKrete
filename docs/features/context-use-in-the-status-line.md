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
- 2026-11-19, decisions with Nicholas Johnson: record the figure in usage.json (recommended); show
  `ctx –` when it's missing (chosen over leaving the part out); never fall back to a saved figure
  (live only, recommended).

## Agreed scope

- **Line.** Inside an app, `bull statusline` ends with `· ctx N%`, after `wk`. N is rounded the same
  way as 5h and wk, and comes only from the live input's `context_window.used_percentage`. When the
  input has no figure (null or absent, early in a session or right after `/compact`), the line shows
  `ctx –`. The ctx part never falls back to the value saved in usage.json; 5h and wk keep their
  fallback. Outside an app the line is still just `bull`.
- **Parsing (claude_code).** `parse_statusline` reads `context_window.used_percentage` into the
  sample's new `context` field. A sample exists when a rate-limit window or the context figure has
  a percentage. An unreadable value counts as no figure. There's no fallback that works the figure
  out from token counts.
- **Recording (usage).** `UsageSample` gains `context: float | None` (0–100). usage.json stays format
  1 with an optional `context` key; a file without the key reads as None. `check()` ignores it.
- **Journeys.** Journey 3 changes: the status line it records also shows `ctx`, and the input
  without a context figure shows `ctx –`. No new journeys.
- **Screens.** None. The status line isn't an app screen, so there's nothing to prototype.
- **Modules.** usage (contract + usage.py), claude_code (parse_statusline in plugin.py), cli
  (statusline.py). No interfaces between parts.
- **Contract changes.** usage: `UsageSample.context: float | None`. claude_code: no change to the
  contract's text (`StatusLineInput.usage` already holds a `UsageSample`); its behavior spec changes.
- **Out of scope.** A warning or colour threshold for high context use; context use in the pause
  check; subagents' context use (its own feature, show-subagents-context-use); the GUI header.
