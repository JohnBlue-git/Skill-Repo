---
name: claude-usage-report
description: Reconstructs an interactive daily/weekly/monthly Claude Code usage and cost dashboard from local session transcripts under ~/.claude/projects, since Claude Code has no persisted usage history beyond /usage's live session/7-day view. Use when the user asks how much Claude/Claude Code usage, spend, cost, or tokens they've used over time, or wants a usage chart, graph, or report.
---

# Claude Code Usage Report

`/usage` only shows the current session and a rolling 7-day window — it doesn't
persist history across sessions. This skill rebuilds that history from the
JSONL transcripts Claude Code already writes locally to `~/.claude/projects/`,
and renders it as an interactive chart.

## Steps

1. Run the build script, writing to your current session's scratchpad
   directory as a staging file — not a permanent path, since step 2 publishes
   it and the file itself doesn't need to outlive that:

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/build_report.py /path/to/scratchpad/usage_report.html
   ```

   If `${CLAUDE_SKILL_DIR}` isn't set in your shell, use the absolute path to
   this skill's directory (printed above this file's contents when the skill
   was invoked) instead — e.g. `~/.claude/skills/claude-usage-report/scripts/build_report.py`.

   Only write it somewhere permanent (e.g. a path under the user's home or
   project directory) if the user explicitly asks to keep a local copy of the
   HTML alongside the published Artifact.

   The script writes a one-line summary to stderr (files scanned, active days,
   estimated total cost). **Check that summary before continuing** — if
   `files scanned` is 0, tell the user there's no local Claude Code history on
   this machine yet rather than publishing an empty chart.

2. Publish the generated HTML with the Artifact tool:
   - `favicon: "📊"`
   - `description`: one sentence naming the date range and estimated total cost
     from the stderr summary.

3. Report the headline numbers back to the user as text (total cost, total
   tokens, active days, the single most expensive period) — don't make them
   click through just to get the summary.

## Tell the user, every time

- Cost is an **estimate** at current per-token API list pricing (from this
  skill's `scripts/pricing.json`) — it is **not** an actual bill on a Pro/Max
  seat (those are flat-rate/rate-limited, not metered per token).
- It only covers **this machine** — a different machine's
  `~/.claude/projects/` isn't included.
- If pricing looks stale (a model migrated, a promo rate expired), say so and
  point at `scripts/pricing.json` rather than silently trusting old numbers.

## If pricing.json looks out of date

Don't guess new rates. Either ask the user, or check current pricing (e.g. via
the `claude-api` skill's model table, or WebFetch of
`https://platform.claude.com/docs/en/pricing`) before editing
`scripts/pricing.json`.

## Extending this skill

See `DESIGN.md` for the architecture and chart design rationale, and
`README.md` for install/usage instructions to hand to someone else.
