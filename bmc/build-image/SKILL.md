---
name: build-image
description: Sync repo and bitbake an obmc-phosphor-image for one or more Insyde BMC firmware platforms, auto-retrying failed recipes with do_cleanall. Use when the user names one or more of these platforms and asks to sync/build/bitbake an image - evb-ast2600-insyde, gb200nvl-bmc-insyde, intel-bhs-insyde, gb300-galaxy-insyde, evb-ast2700-a2-insyde, pmc-ast2700-a2-insyde, vr-c2-bmc-insyde, vr-nvl-bmc-insyde, intel-ast2700-insyde, sp7-insyde, pmc-insyde - or their root dirs (opf2, GB300-Galaxy, EVB2700_A2, Vera, OKS, AMDShared).
---

# build-image

Sync a Yocto/OpenBMC source tree and bitbake `obmc-phosphor-image` for one or
more platforms, self-healing recipe build failures by `do_cleanall`-ing the
failed recipe and retrying — until the build succeeds or the same recipe
fails twice in a row (a sign of a real bug, not a stale-state problem).

Invoke this skill with the platform name(s) to build, e.g. `evb-ast2600-insyde`
or `vr-c2-bmc-insyde gb200nvl-bmc-insyde`. Never guess which platform(s) to
build — if not given any, ask.

## Platform config

The platform → root dir mapping lives in this skill's `platforms.json`, not
in this file — read it fresh each run instead of assuming a memorized list,
since it can be edited independently of these instructions. Schema:

```json
{
  "remote_build_host": "user@host",
  "platforms": {
    "<setup arg>": { "root": "<root dir>", "remote": true|false, "image": "<optional, defaults to obmc-phosphor-image>" }
  }
}
```

- `root`: the source tree root for that platform. A `~/...` path is local to
  this machine; `remote: true` entries hold a path on `remote_build_host`
  instead (see below).
- `remote`: whether this platform's root lives on the remote build host.
- `image`: only needed when a platform bitbakes something other than
  `obmc-phosphor-image` (e.g. `intel-bhs-insyde` → `intel-platforms`). Pass
  it as the `image` arg (`$4`) to `bitbake-loop.sh`; omit the arg entirely
  when the entry has no `image` field.

To add, remove, or repoint a platform, edit `platforms.json` — don't hardcode
mappings into these instructions. If you add or rename a platform, also
update this skill's frontmatter `description` (the platform-name list there
drives when the skill gets invoked) so it stays in sync.

If a requested platform isn't in `platforms.json`, or its root dir doesn't
exist (locally, or on the remote host for `remote: true` entries), skip it
and say so — don't error out the whole run over it.

### Remote platforms (`remote: true` in platforms.json)

A `remote: true` platform's `root` is a path *on* `remote_build_host` from
`platforms.json`, not on this machine. Both scripts take the remote target
as their last argument — pass `platforms.json`'s `remote_build_host` value
as the last arg to `repo-sync.sh`/`bitbake-loop.sh` whenever the platform (or
the root it shares) has `remote: true`. Omit that arg (leave it empty) for
every `remote: false` platform — those still build locally.

This requires passwordless key-based ssh auth to `remote_build_host` already
set up — the scripts use `BatchMode=yes` and will fail fast rather than hang
on a password prompt. If a run fails immediately with "ssh key auth not set
up?", set it up once with:

```
ssh-copy-id -i ~/.ssh/id_rsa.pub <remote_build_host>
```

(run from a machine/network that can actually reach that host — this can't
be done from inside a build-retry loop). Never ask for or hardcode the
account's password anywhere in these scripts or logs.

## Why this needs two scripts, not inline bash

- Bash tool calls don't share shell state — sourcing `setup <platform>`
  (which puts `bitbake` on `PATH` and `cd`s into the build dir) in one call
  is invisible to the next call. So setup + the whole build-retry loop must
  happen inside a *single* script invocation.
- A full image build can run for hours — far past any single foreground
  command's timeout. Run each script with Bash `run_in_background` and let
  the harness's completion notification tell you when it's done. Do **not**
  poll it and do not use `ScheduleWakeup`/sleep loops to check on it.
- `repo sync` is per source **tree**, not per platform. If several requested
  platforms share a `root` value in `platforms.json` (e.g. multiple entries
  pointing at the same remote tree), sync that root *once*, then fan out to
  per-platform builds — don't run `repo sync` redundantly (and never in
  parallel with another sync on the same tree).
- For `remote: true` platforms, each `ssh` call is its own fresh shell just
  like each Bash tool call is — so `cd`+`source setup` has to be re-chained
  onto *every* remote `bitbake` invocation inside the script, not sourced
  once and reused. `bitbake-loop.sh` already does this when `remote_host` is
  set.

Scripts (in this skill's `scripts/` dir):
- `repo-sync.sh <root_dir> <log_file> [remote_host]` — runs `repo sync`,
  logs, ends with a `RESULT: SYNC_SUCCEEDED (...)` or `RESULT: SYNC_FAILED
  (...)` line.
- `bitbake-loop.sh <root_dir> <setup_arg> <log_file> [image] [max_attempts]
  [remote_host]` — sources `setup <setup_arg>`, then loops: `bitbake <image>`
  → on failure, extract the failing `recipe:task` from the log, `bitbake
  -b <recipe> -c cleanall`, retry. Ends with a `RESULT: BUILD_SUCCEEDED
  [...]` or `RESULT: STOPPED [...]` / `RESULT: BUILD_FAILED [...]` line.
  `image` defaults to `obmc-phosphor-image`; `max_attempts` defaults to 20.
  `remote_host` (e.g. `user@host`) runs `repo sync`/`setup`/`bitbake` over
  ssh on that host instead of locally — pass `platforms.json`'s
  `remote_build_host` here for any `remote: true` platform, omit it for
  every `remote: false` platform.

Both scripts are self-contained bash — no state from prior Bash calls needed,
so it's safe to launch them directly with `run_in_background: true`.

## Procedure

1. Read `platforms.json` fresh and resolve each requested platform against
   it, **preserving the order the user listed them in**. Report any that
   don't match an entry, and any whose root dir is missing, as skipped (drop
   them from the order, don't halt the run).
2. Pick a log file per root and per platform under the scratchpad dir, e.g.
   `<scratchpad>/sync-<rootname>.log` and `<scratchpad>/build-<platform>.log`.
3. Decide sequential vs. parallel:
   - **Default: strict left-to-right sequential**, one platform at a time,
     in the order resolved in step 1 — regardless of which root each
     platform lives under. This is what to do unless the user explicitly
     asked for platforms to run "at the same time" / "in parallel" /
     "concurrently" with no ordering requirement.
   - **Parallel: only if the user explicitly asked for it.** In that case,
     group by root, sync each unique root once (parallel tool calls across
     roots), then launch every platform under a successfully-synced root
     concurrently. Skip building under any root whose sync failed.
4. **Sequential mode walkthrough** (the default): keep a set of "roots
   synced this run" (starts empty). For each platform in order:
   a. If its root isn't in the synced set yet, launch
      `bash <skill_dir>/scripts/repo-sync.sh <root_dir> <sync_log>
      [remote_build_host]` with `run_in_background: true` and wait for its
      completion notification (don't poll) — append `platforms.json`'s
      `remote_build_host` only when this platform's entry has `remote: true`.
      Add the root to the synced set. If `RESULT: SYNC_FAILED`, report it
      and skip this platform (and any later platform under the same root)
      — move on to the next platform whose root differs.
   b. Launch `bitbake-loop.sh` for this platform with `run_in_background:
      true` (pass the entry's `image` field as the `image` arg if present,
      omit the arg entirely otherwise; and append `remote_build_host` as the
      trailing arg when the entry has `remote: true`, omit it otherwise),
      and wait for its completion notification before moving to the next
      platform in the list. This is what makes the order strict: platform
      *N+1* never starts until platform *N* has a final `RESULT:`.
   c. Report that platform's outcome immediately (don't hold it back for
      the final summary), then continue to the next one.
5. When each `bitbake-loop.sh` finishes, read its log's final `RESULT:` line
   and report per-platform: succeeded (with attempt count), or stopped/failed
   (with the failing recipe and why, e.g. "same recipe failed twice — needs
   manual triage" or "couldn't identify the failing recipe — see log").
6. Give a final summary across all requested platforms once every
   root/platform in the run has reported.

Do not open the raw log files proactively to narrate build progress line by
line — the scripts already collapse each attempt down to `RESULT:` markers;
skim the log with `grep RESULT: <log>` or `tail` only if a `STOPPED`/`FAILED`
result needs more detail for the report.
