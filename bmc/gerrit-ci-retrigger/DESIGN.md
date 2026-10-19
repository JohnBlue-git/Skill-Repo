# Design

## Architecture

```
Claude (SKILL.md procedure)
  │
  ├─ list_open_changes.py ──► `ssh gerrit.insyde.com gerrit query` (JSONL)
  │                            scans each change's comments for
  │                            bema.insyde.com/job/<name>/<build> links
  │
  ├─ check_build.py (per job) ─► CI /api/json (status)
  │                              CI /consoleText (tail-only, if failed)
  │                              → regex classification
  │
  ├─ report.py                 orchestrates the two above, prints a table,
  │                            writes {id: build_url} to an index file
  │
  └─ retrigger.py (per chosen ID) ─► POST CI /<build_url>/gerrit-trigger-retrigger-this/index
```

Everything is a small, separately-runnable Python 3 stdlib script (no
`requests`, no dependencies to install) so Claude can invoke each stage via
Bash and read its stdout/JSON directly, the same pattern the `build-image`
skill uses for its shell scripts.

## Why Python instead of bash (unlike `build-image`)

`build-image`'s scripts are bash because their job is running/retrying
`bitbake` — spawning processes and grepping logs, which bash already does
well. This skill's job is talking to two REST APIs and parsing JSON plus
semi-structured log text — `curl | jq | grep` chains get unreadable fast
once you need "the last matching recipe path in the tail of a multi-MB
log," so plain Python with `re` and `json` is the simpler tool here, not a
speculative choice.

## Gerrit access: SSH, not REST

The original plan was the Gerrit REST API authenticated with a generated
HTTP password. Tested against the real account and it doesn't exist here:
Settings has no "HTTP Credentials" entry at all (Profile, Preferences,
Notifications, Email Addresses, SSH Keys, Groups, Identities only) — this
account is LDAP/SSO-backed and Gerrit isn't offering a separate token for
it. Confirmed via `curl -u user:pass .../a/accounts/self` → 401, with the
server's own `WWW-Authenticate: Basic realm="Gerrit Code Review"` header
proving the auth *scheme* sent was right and only the credential was
rejected/nonexistent.

What does work: this Gerrit (3.12.0) still runs the long-deprecated `gerrit
query` SSH command, authenticated by an SSH key already registered under
Settings → SSH Keys (the same key used for `git push`/`git review`). No
new credential to generate — `gerrit_ssh_query()` in `_common.py` just
shells out to:
```
ssh -p 29418 <GERRIT_USER>@gerrit.insyde.com gerrit query --format=JSON --comments "<query>"
```
and parses the JSONL result (one JSON object per matching change, plus a
trailing `{"type":"stats",...}` line that's dropped). Confirmed end-to-end
against the real dashboard.

## How a Gerrit change maps to a CI build

Gerrit itself doesn't know about Jenkins. The link exists because the
Jenkins **Gerrit Trigger plugin** (confirmed — build JSON shows
`com.sonyericsson.hudson.plugins.gerrit.trigger.hudsontrigger.GerritCause`)
posts comments back onto the change as it triggers and completes builds,
e.g.:
```
Patch Set 3:

Build Started https://bema.insyde.com/job/BMC_OPF2.0-GB300_CEC173X-pfr/2346/ (4/8)
```
and, once all jobs for that patch set finish, a single summary comment
listing every job's result:
```
Patch Set 3: Verified-1

Build Failed

https://bema.insyde.com/job/BMC_OPF2.0-GB300_CEC173X-pfr/2346/ : FAILURE
https://bema.insyde.com/job/BMC_OPF2.0-NVIDIA-gb300-bianca/6797/ : FAILURE
https://bema.insyde.com/job/BMC_OPF2.0-Intel-bhs-advanced/12498/ : SUCCESS
...
```
`list_open_changes.py` regex-scans every comment's text for
`https://bema.insyde.com/job/<name>/<build>/` and, per job name, keeps the
highest build number seen (the most recent run for that job) — confirmed
against real changes in `Supervyse-OPF/bmcweb-override`. It deliberately
does **not** parse the `: SUCCESS`/`: FAILURE` suffix from that summary
comment even though it's right there — `check_build.py`'s direct call to
the CI's own `/api/json` is already the authoritative status (and is
needed anyway to fetch the console log on failure), so parsing status out
of Gerrit's comment text too would just be a second, redundant source of
truth for no benefit.

`CI_URL_HOST` is an env var override for the CI hostname, for the (now
unlikely, but still possible) case a different project links a different
CI host.

## Error classification

`check_build.py` fetches only the **tail** of the console log (last
~300 KB, `MAX_CONSOLE_TAIL` in `_common.py`) rather than the whole thing —
bitbake logs on these platforms can run into the tens of MB, and the
failure summary is always the last thing printed, so downloading the rest
buys nothing. It's a streamed download that discards everything except the
tail as it goes (not an HTTP Range request — Jenkins' `consoleText`
endpoint is dynamically generated and Range support on it isn't something
to rely on).

Classification order (first match wins), run against that tail:

1. **Conflict** — regexes for `CONFLICT (`, `Automatic merge failed`,
   `Merge conflict in`, `cannot fast-forward`, `repo sync.*failed`, etc.
   Checked first because a sync/merge failure means bitbake never ran, so
   the log is short and otherwise clean — no risk of a stray string in
   bitbake output shadowing it.
2. **Recipe build fail** — matches the standard Yocto/OpenBMC failure log
   path:
   ```
   .../work/<arch>/<recipe>/<version>/temp/log.do_<task>.<pid>
   ```
   which bitbake always prints for a failed task, and which also appears
   in the final `Summary: N tasks failed:` block at the very end of the
   log. The **last** match in the tail is used (closest to the end =
   the actual root-cause task, not an earlier transient one). If the
   recipe name contains `bmcweb`, it's reported as `bmcweb_build_fail`
   specifically (per the user's request to call that out separately);
   otherwise `recipe_build_fail` with the recipe/task named.
3. **Other** — anything that reported non-`SUCCESS` but matched neither
   pattern. Reported with a 25-line excerpt of the tail (last 25 non-blank
   lines) plus the `consoleText` URL, on the assumption a human glance
   beats a wrong guess.

This is necessarily heuristic — it's pattern matching over free-form build
output, not a structured error API. Expect to tune the regexes once they've
been run against a batch of real failures; `check_build.py` is the only
file that would need changes.

## Retrigger mechanism (confirmed)

The original plan — scrape the build page HTML for an `<a href>` containing
"retrigger" — doesn't work against this Jenkins (2.555.3): it's a modern
JS-rendered "two-column" UI where sidebar action buttons are populated
client-side from the build's `actions` API, not emitted as static anchors.
`discover_retrigger.py`'s scrape came back empty against a real build,
confirming this rather than just theorizing it.

The real endpoint was obtained by capturing an actual browser click in
DevTools Network tab:
```
POST <build_url>/gerrit-trigger-retrigger-this/index
→ 302 (redirect back to the build page) on success
```
`retrigger.py` POSTs there directly, attaching a CSRF crumb (from
`<jenkins_base>/crumbIssuer/api/json`) if the instance issues one.

**One-shot behavior, confirmed by observation:** after a successful
retrigger, the "Retrigger" button disappears from that build's page. It's
a consumed action, not a repeatable one — retriggering the same
already-retriggered build again is expected to fail. That's not a sign the
endpoint is wrong; it means there's nothing left to fire from that specific
build page (the new build gets its own page, with its own fresh button).

`discover_retrigger.py` is kept only for the case a *different* CI
instance/job type exposes the button differently (e.g. an older
classic-UI Jenkins where it might really be a static link) — not needed
for bema.insyde.com.

## Why one batch confirmation, not per-patch or fully automatic

Per your answer: the report is shown once, you name the set to retrigger in
one go, the skill reads that back to you once more before firing anything,
then executes the whole set without asking again per item. This is
`SKILL.md` step 5 — it's a conversational check, not a tool-level one,
because the set size is unbounded and doesn't fit `AskUserQuestion`'s
4-option limit.

## Explicitly out of scope for v1

Not built, and not planned unless asked for:

- Posting results back as Gerrit comments/votes.
- Any notification channel (Slack/email) — this is a pull-when-asked skill.
- Persisting report history across runs — each run's index file is
  overwritten by `report.py` and only meant to live for that conversation
  (hence writing it into the session scratchpad, never `/tmp`).
- Auto-retriggering anything without the user naming it. `SKILL.md`
  explicitly forbids treating an ambiguous or silent answer as "all."
- Non-token CI auth (plain username/password) — dropped once the API
  token was confirmed working.

## Credential handling

`GERRIT_USER` and `CI_USER`/`CI_API_TOKEN` are read straight from
environment variables by `_common.py` at call time. Gerrit access has no
separate secret to hold at all — it rides on whichever SSH key is already
loaded/registered for the user, resolved by `ssh` itself the normal way, so
there was no `GERRIT_HTTP_PASSWORD` to keep secure even conceptually. No
script writes a credential to a file, includes one in the index file, or
prints it (errors print HTTP/SSH status codes and URLs, never secrets).
`require_env()` fails fast with a pointer to README.md rather than
prompting for a credential inline.

## Handling a stale CI link (build pruned by Jenkins retention)

Real data surfaced this: an old Gerrit comment can point at a build number
Jenkins has since garbage-collected (its normal retention policy), giving
a 404 on `/api/json`. The first version of `check_build.py` let that
propagate as a fatal error, which — since `report.py` calls it once per
job across every open change — killed the *entire* report over one stale
link in one old change. Fixed by having `check_build.py` catch the 404
(and any other CI HTTP error) itself and report a `NOT_FOUND` /
`CI_ERROR_<code>` row instead of dying, so one bad link costs one table row,
not the whole run. `_common.ci_get_json` was correspondingly simplified to
just let `HTTPError` propagate — the caller is in the better position to
decide whether a given failure is fatal or just one row to skip.
