# claude-usage-report

A Claude Code [Skill](https://code.claude.com/docs/en/skills) that turns your
local session logs into a real weekly/monthly usage & cost dashboard —
something Claude Code doesn't otherwise persist (`/usage` only shows the
current session plus a rolling 7-day window).

It works by reading the JSONL transcripts Claude Code already writes to
`~/.claude/projects/` on every session, summing up token usage per day, and
estimating cost at current API pricing. Nothing is sent anywhere — it's a
local script producing a local HTML file.

## What you get

An interactive, self-contained HTML page (dark/light aware, no external
dependencies) with:

- Stat tiles: estimated total cost, total tokens, message count, active days
- A bar chart toggling between **Daily / Weekly / Monthly** and **Cost / Tokens**
- Hover tooltips per bar, and a plain-table view for anything a chart hides

See [DESIGN.md](DESIGN.md) for why it's built this way.

## Install

**For yourself, in every project** — copy this folder to your personal skills
directory (auto-discovered immediately, no restart):

```bash
cp -r claude-usage-report ~/.claude/skills/
```

**For one project only** — copy it into that project instead:

```bash
cp -r claude-usage-report /path/to/project/.claude/skills/
```

**Sharing with someone else** — this whole folder *is* the package. Zip it,
`git init` it, hand it over, whatever — the recipient just copies it to one of
the two locations above on their own machine. There's no build step and no
external dependencies beyond a `python3` on PATH (standard library only).

## Use it

Fastest way — type the slash command directly:

```
/claude-usage-report
```

Or just ask in plain language; the skill's `description` (in `SKILL.md`) is
written to auto-trigger on requests like:

> "How much have I used Claude Code this month?"
> "Show me a graph of my token usage"
> "What's my weekly Claude spend been?"

Either way, Claude runs `scripts/build_report.py`, publishes the result as an
Artifact, and reports the headline numbers back in chat.

**Where the HTML file goes:** `build_report.py` writes to whatever path it's
given — per `SKILL.md`, Claude points that at a scratch/staging location (e.g.
your current session's scratchpad directory), not a fixed permanent path. That
file is just the input to the Artifact publish step and isn't meant to
outlive the session. The durable, shareable output is the published Artifact
link. If you want a persistent local copy of the HTML too, say so — e.g. "also
save it to `~/reports/claude-usage.html`" — and Claude will write it there
instead of (or in addition to) the scratch copy.

## Run it yourself, without Claude

The scripts are plain Python (stdlib only) — useful if you want the raw JSON,
or to wire this into something else (a cron job, a static site, whatever):

```bash
# Just the aggregated per-day JSON, to stdout
python3 scripts/parse_usage.py

# ...or straight to a file
python3 scripts/parse_usage.py usage_daily.json

# The full rendered HTML report
python3 scripts/build_report.py usage_report.html
```

## Keeping pricing current

Token pricing lives in [`scripts/pricing.json`](scripts/pricing.json), not
hardcoded in the scripts — edit it directly when Anthropic changes rates or
you start using a model that isn't listed. Unlisted models fall back to the
`default` entry, so an unrecognized model ID doesn't break the build, but its
cost will be wrong until you add it.

## Limitations

- **Estimate, not a bill.** If you're on a Claude Pro/Max seat, actual billing
  is flat-rate/rate-limited, not metered per token — this cost is a proxy for
  relative usage weight, not a receipt.
- **This machine only.** It reads local files; usage from another machine
  or a teammate's account isn't included.
- **`<synthetic>` messages are zero-cost.** Claude Code inserts some non-LLM
  synthetic messages (command wrappers, etc.) into transcripts; these carry
  no real token cost and are excluded from pricing.
