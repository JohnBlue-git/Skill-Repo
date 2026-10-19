# Design notes

## Why this exists

Claude Code's only built-in usage view is `/usage`: a live session cost plus a
rolling 7-day breakdown. There's no persisted "show me last month" — but every
session is already logged locally as JSONL under `~/.claude/projects/`, with
per-message token usage (`message.usage.{input_tokens,output_tokens,
cache_creation_input_tokens,cache_read_input_tokens}`) and a `timestamp`. That's
enough to reconstruct a full history without calling any API — this skill is
just the aggregation and rendering layer on top of data that already exists on
disk.

## Architecture

```
~/.claude/projects/**/*.jsonl   (source of truth — every project, every session)
        │
        ▼
scripts/parse_usage.py          walks every transcript line, keeps only
                                 assistant messages with a usage block,
                                 buckets by (day, model)
        │
        ▼
scripts/pricing.json            $/MTok per model + cache read/write multipliers
                                 (kept as data, not code, so rates are a one-line
                                 edit rather than a script change)
        │
        ▼
scripts/build_report.py         computes cost per (day, model), sums to daily
                                 totals, injects into the HTML template
        │
        ▼
templates/usage_report.html     self-contained chart — the __DAILY_DATA__
                                 placeholder is the only thing build_report.py
                                 touches; everything else (aggregation into
                                 weeks/months, rendering) happens client-side
```

Aggregating by `(day, model)` rather than just `day` matters: pricing is
per-model, and a single day can mix models (e.g. Sonnet for the main work,
Haiku for a subagent). Cost is computed per bucket, then summed — never a
single blended rate applied to a day's total tokens.

Weekly and monthly rollups are *not* precomputed in Python — the template
receives only the daily series and buckets it into ISO weeks (Monday start)
and calendar months in JavaScript. One source of truth (`DAILY_RAW`), three
views, no drift between them.

## The cost model

Cost per `(day, model)` bucket:

```
cost = input_tokens        × price.input
     + output_tokens       × price.output
     + cache_1h_tokens     × price.input × 1h_write_multiplier   (2.0×)
     + cache_5m_tokens     × price.input × 5m_write_multiplier   (1.25×)
     + cache_read_tokens   × price.input × read_multiplier       (0.1×)
```

Cache-write tokens are split into 1-hour and 5-minute TTL buckets because
Claude Code predominantly uses 1-hour ephemeral caching for its system
prompt/tools, and the two TTLs price differently (2× vs 1.25× base input).
Transcripts from before this breakdown existed fall back to treating all
cache-write tokens as 5-minute (the API's default TTL when unspecified) —
see the `if cc: ... else: ...` branch in `parse_usage.py`.

`<synthetic>` is priced at $0/$0 — it's Claude Code's internal label for
non-LLM messages (e.g. command-wrapper output) that show up in the transcript
stream but never hit the API.

**This is an estimate, not a bill** — see the Limitations section in
`README.md`. It's most useful as a *relative* signal (which week was heavy,
which model dominates) rather than a reconciled dollar figure.

## Chart design

Built directly against Anthropic's `dataviz` skill method (form → color →
validate → marks → interaction → accessibility), not an off-the-shelf
charting library — the whole thing is self-contained SVG + vanilla JS so it
runs as a single HTML file with zero dependencies.

- **Form**: this is a magnitude-over-time job with discrete periods (day/week/
  month), so bars, not a line — a line implies interpolation between points
  that doesn't mean anything here (there's no "usage" between two calendar
  days).
- **Single series → no legend.** Only one metric is plotted at a time (cost or
  tokens, chosen via the segmented control); per the dataviz skill's rule, a
  single series needs no legend box — the chart title and axis already name
  it. Cost and tokens are deliberately *not* stacked or dual-axised (dual-axis
  is flagged as the #1 charting mistake in the skill) — they're two mutually
  exclusive views of the same bars instead.
- **Color**: the reference palette's categorical slot 1 (`#2a78d6` light /
  `#3987e5` dark) — the same hue the palette designates as the default
  *sequential* color for single-hue magnitude encoding, so this chart is using
  it in exactly the role it was validated for.
- **Marks**: bars are a hand-rolled SVG `<path>` (`roundedTopPath()`) rather
  than a plain `<rect>`, so the rounding (4px) only applies to the top corners
  — the end away from the baseline — leaving the bottom edge flush to the
  axis, per the skill's mark spec. A `<rect>`'s uniform `rx` would round all
  four corners, which reads as the bar "floating."
- **Interaction**: a full-height invisible hit-rect sits behind each bar so
  the hover target is much larger than the visible bar (important once you're
  at 25+ daily bars in a narrow chart) — the visible bar dims to indicate
  hover instead of a hard color swap.
- **Zero-filling**: the daily series fills every calendar day in range, not
  just active ones — an idle stretch (a vacation, a week off) should read as a
  visible gap of zero-height bars, not silently vanish and compress the
  timeline.
- **Accessibility**: a "View as table" toggle renders the exact same
  aggregation as a plain HTML table — the skill's requirement that a table
  view always exists alongside the chart, not just on request.
- **Light/dark**: every color is a CSS custom property with both a
  `prefers-color-scheme: dark` block and a `data-theme="dark"` override (for
  an explicit in-page theme toggle, if the host page has one) — never a single
  fixed palette.

## Extending

- **New model / pricing change**: edit `scripts/pricing.json` only — no code
  changes needed. Unlisted models fall back to the `default` entry.
- **Different aggregation window** (e.g. a 4-week rollup): add another
  `aggregate(keyFn, labelFn)` call in the template's `<script>` and a new
  button in the `period` segmented-control group — the rendering, tooltip, and
  table code all key off `SERIES[state.period]` and don't need to change.
- **A second machine's history**: `parse_usage.py` takes an optional
  `claude_dir` argument to `compute_usage()` if you want to point it at a
  different `.claude` directory (e.g. a synced copy) instead of `~/.claude`.
- **Restyle**: every visual value is a CSS custom property on `.viz-root` —
  swap the `--series-1` (and its dark counterpart) for a different validated
  palette slot; don't hand-pick a new hex without running it through the
  dataviz skill's `validate_palette.js` first.
