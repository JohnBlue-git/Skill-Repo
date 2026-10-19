# gerrit-ci-retrigger

Checks every open patch on your Gerrit dashboard, reports whether its CI
build passed or failed (and why), and retriggers whichever ones you pick.

- Gerrit: `gerrit.insyde.com`
- CI: `bema.insyde.com` (a Jenkins instance, linked from CI comments on
  each change)

For how this actually works under the hood — API calls, error
classification rules, and which parts are still unverified assumptions —
see [DESIGN.md](DESIGN.md).

## Prerequisites

- Your machine can reach `gerrit.insyde.com` and `bema.insyde.com` directly
  (VPN connected, etc.) — the same way your browser reaches them today.
- Python 3 (stdlib only, no extra packages to install).

## Credentials

Two separate credentials are needed, using two different mechanisms —
Gerrit and the CI turned out to need different approaches once tested
against the real instances (see DESIGN.md for how this was worked out).

### 1. Gerrit: your username + an SSH key already registered with Gerrit

This Gerrit account is LDAP/SSO-backed and has no "HTTP Credentials" /
generated password option at all — Settings only shows Profile,
Preferences, Notifications, Email Addresses, SSH Keys, Groups, Identities.
So Gerrit access uses **SSH**, not the REST API:

1. `GERRIT_USER` is your Gerrit **Username**, shown on Settings → Profile
   (not your email, not your display name).
2. You need an SSH key already registered under Settings → **SSH Keys**
   whose private half is available locally (typically `~/.ssh/id_rsa` or
   another key ssh already tries by default — the same key you use for
   `git push`/`git review` to this Gerrit works). No new key needs
   generating if one's already there and valid.
3. Confirm it works:
   ```bash
   ssh -p 29418 -o BatchMode=yes "$GERRIT_USER@gerrit.insyde.com" gerrit version
   ```
   Should print something like `gerrit version 3.12.0`. If it hangs or
   fails, your key isn't registered/loaded — check `ssh-add -l` or pass
   `-i /path/to/key` and register that key's `.pub` under SSH Keys.

### 2. CI (bema.insyde.com): username + API token

1. Go to `https://bema.insyde.com`, log in if needed.
2. Click your name (top right corner). Your username — shown there, or in
   the URL of your user page (`.../user/<username>/`) — is `CI_USER`.
3. From that user page, click **Configure** in the left sidebar (some
   Jenkins themes label it **Security** instead).
4. Find the **API Token** section → **Add new Token**. Give it a name
   (e.g. `gerrit-ci-retrigger`) and click **Generate**. Copy the token
   immediately — shown once. That's `CI_API_TOKEN`. Confirmed working via
   Basic auth against both `/api/json` and `/consoleText`.

### Set them as environment variables

Add to your `~/.bashrc`, **above** the `case $- in *i*) ;; *) return;; esac`
non-interactive guard near the top of the file (if the lines go below that
guard, non-interactive shells — including Claude Code's own tool calls —
never reach them and the vars stay unset). Use **single quotes**, not
double quotes — a value containing `$` (e.g. a token like `$BTy...`) gets
silently mangled by variable expansion inside double quotes:

```bash
export GERRIT_USER='your-gerrit-username'
export CI_USER='your-bema-username'
export CI_API_TOKEN='paste-the-api-token-here'
```

No `GERRIT_HTTP_PASSWORD` — Gerrit auth rides on your existing SSH key
instead, nothing to generate or store for it.

The skill never writes these to disk itself and never logs them. Treat this
shell config file like any other secret — don't commit it, don't paste its
contents into chat.

#### Gotcha: Claude Code's Bash tool won't auto-pick these up

Claude Code runs each Bash command against a shell snapshot taken when the
session started, not a fresh login shell — so it does **not** re-read
`~/.bashrc` on its own, even after the vars above are set correctly. Claude
needs to explicitly `source ~/.bashrc` inside the *same* command as the
script it's running, every time (shell state doesn't carry over between
separate tool calls either), e.g.:

```bash
source ~/.bashrc && python3 report.py --index-file <path>
```

If you're running the scripts yourself in a normal terminal, this doesn't
apply — opening a new terminal (or a fresh `source ~/.bashrc`) is enough.

If you'd rather not keep these in your shell profile long-term, you can
instead `export` them just in the terminal session you're running Claude
Code from — they'll only last for that session.

## Usage /gerrit-ci-retrigger

Just ask, in the same terminal/session where those env vars are set:

> "Check my Gerrit patches"
> "What's the CI status on my open changes?"
> "Retrigger 111892 ast2700evb-A2 #511"
> "Retrigger 111892"

The skill will:

1. List your open changes (default scope: changes **you own**, i.e.
   `owner:self status:open` — tell it if you want a different scope, e.g.
   changes you're only reviewing, or a specific project).
2. For each one, find the CI job(s) linked in its comments and check the
   latest build's result.
3. If a build failed, classify why:
   - `bmcweb` build fail
   - `<recipe>` build fail (with the failing task, e.g. `do_compile`)
   - merge/repo-sync conflict
   - other (unclear from the log — you'll get a link to the console output
     and a short excerpt to judge yourself)
4. Show you the full report, then ask which patches to retrigger. You can
   say things like "2 and 5", "all failed", "all the recipe fails", or
   "none".
5. Confirm the exact set once, then fire the retrigger and report per-job
   OK/FAIL.

## Retrigger endpoint

Confirmed against a real build (captured an actual browser click in
DevTools): `POST <build_url>/gerrit-trigger-retrigger-this/index`, 302 on
success. `retrigger.py` uses this directly. Note the button disappears
from the build page after a successful retrigger — it's a one-shot action,
so retriggering the same already-retriggered build again will fail (not a
bug in the endpoint, just nothing left to fire).

## Manual script usage (without going through chat)

```bash
cd ~/.claude/skills/gerrit-ci-retrigger/scripts

# List your open changes and their linked CI jobs
python3 list_open_changes.py --query "owner:self status:open"

# Check one build
python3 check_build.py https://bema.insyde.com/job/<name>/<number>

# Full report + write an index file for retrigger.py
python3 report.py --index-file /tmp/report.json

# Retrigger by row ID from that report
python3 retrigger.py --index-file /tmp/report.json --ids 2,5

# Or retrigger a build URL directly
python3 retrigger.py https://bema.insyde.com/job/<name>/<number>

# Dry-run (prints what it would do, sends nothing)
python3 retrigger.py --dry-run https://bema.insyde.com/job/<name>/<number>
```
