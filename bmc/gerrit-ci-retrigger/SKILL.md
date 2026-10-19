---
name: gerrit-ci-retrigger
description: Check the CI (build) status of all open Gerrit patches under gerrit.insyde.com, classify why any failed (bmcweb build fail, <recipe> build fail, merge conflict, other), and retrigger selected ones. Use when the user asks to check their Gerrit patches/dashboard, check CI/build status, or wants to retrigger a Jenkins build linked from a Gerrit change.
---

# gerrit-ci-retrigger

Reports the CI status of every open patch on the user's Gerrit dashboard
(gerrit.insyde.com), with a best-effort reason for any failure, then lets
the user pick which to retrigger on the CI (bema.insyde.com).

Read `README.md` (setup/credentials) and `DESIGN.md` (how each piece works
and what's been confirmed against the real instances vs. still assumed)
alongside this file before running it for the first time.

## Before running

The Bash tool runs against a shell snapshot taken at session start, not a
fresh login shell — it will **not** see vars added to `~/.bashrc` after that
unless each command explicitly `source ~/.bashrc` first (state doesn't
persist between separate Bash calls either, so this must be repeated per
call, not done once). Every command below must therefore be
`source ~/.bashrc && <the actual command>`, not the bare command.

Check the three required env vars are set this way: `GERRIT_USER`,
`CI_USER`, `CI_API_TOKEN` (Gerrit auth rides on an already-registered SSH
key, not an env var — see README.md). If any is missing even after
sourcing, stop and point the user at README.md's "Credentials" section
instead of asking them to paste secrets into chat.

## Procedure

1. Pick an index file path under this session's scratchpad directory, e.g.
   `<scratchpad>/gerrit-ci-report.json`. Never use `/tmp` directly.
2. Run:
   ```
   source ~/.bashrc && python3 <skill_dir>/scripts/report.py --index-file <scratchpad>/gerrit-ci-report.json
   ```
   Default query is `owner:self status:open`. If the user wants patches
   they're only reviewing too, pass `--query "status:open"` (or whatever
   query they ask for — never guess silently if they name a different
   scope, e.g. a specific project).
3. Turn the table into a readable report grouped by change: change number +
   link, subject, and per-CI-job status. For anything not `SUCCESS`, state
   the classified reason plainly:
   - `bmcweb_build_fail` → "bmcweb build failed"
   - `recipe_build_fail` → "`<recipe>` build failed (task `<task>`)"
   - `conflict` → "merge/sync conflict"
   - `other` → "unclear from the log — needs a manual look" (include the
     `console_url` and the short excerpt so the user can judge)
   - `NO_CI_LINK_FOUND` → say so plainly; don't guess a status. This means
     no comment on the change contained a `bema.insyde.com/job/.../N/` link.
   - `NOT_FOUND` → the build a comment linked to no longer exists (pruned by
     Jenkins retention, most common on old changes) — report it as stale,
     not as a failure, and don't offer it as retriggerable.
4. Ask the user which to retrigger, in plain conversation (not
   AskUserQuestion — the option count is unbounded and doesn't fit its
   4-option limit). Accept things like "2 and 5", "all failed", "all
   recipe fails", "none". Resolve their answer to a set of row IDs from the
   table yourself; don't ask them to type raw URLs.
5. Confirm the resolved set back once in plain language ("retriggering IDs
   2, 5: <job> for change 111971, <job> for change 111982— go ahead?")
   before firing anything — this is the one batch confirmation the user
   asked for, not a per-patch prompt.
6. On confirmation, run:
   ```
   source ~/.bashrc && python3 <skill_dir>/scripts/retrigger.py --index-file <scratchpad>/gerrit-ci-report.json --ids <comma-separated ids>
   ```
   Report each line's OK/FAIL back to the user verbatim-ish. A FAIL here
   usually means either the build was already retriggered once before (it's
   a one-shot action — see DESIGN.md) or a permissions issue, not a wrong
   URL (the endpoint itself is confirmed). Don't retry blindly.
7. Never retrigger anything the user didn't explicitly select, and never
   treat silence or an ambiguous answer as "retrigger all."
