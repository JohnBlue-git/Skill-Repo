"""Shared HTTP/auth/SSH helpers for the gerrit-ci-retrigger skill scripts.

Credentials come from environment variables only - never hardcode them,
never print them, never write them into any cache/index file.
"""
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

GERRIT_HOST = os.environ.get("GERRIT_HOST", "gerrit.insyde.com")
GERRIT_SSH_PORT = os.environ.get("GERRIT_SSH_PORT", "29418")
CI_URL_HOST_DEFAULT = "bema.insyde.com"

# Cap on how much of a build's console log we keep in memory (tail bytes).
# Bitbake logs can be huge; the failure summary is always at the end, so we
# stream and discard everything except the last MAX_CONSOLE_TAIL bytes.
MAX_CONSOLE_TAIL = 300_000


def die(msg, code=1):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def require_env(names):
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        die(
            "missing required environment variable(s): "
            + ", ".join(missing)
            + "\nSee README.md 'Credentials' section for how to generate and set these."
        )


def _basic_auth_header(user, secret):
    token = base64.b64encode(f"{user}:{secret}".encode()).decode()
    return f"Basic {token}"


def gerrit_ssh_query(query, comments=True):
    """Run `gerrit query` over ssh and return the list of matching changes.

    This Gerrit instance has no HTTP Credentials / generated password for
    this account (LDAP/SSO-backed) - the REST API's Basic auth is
    unreachable, so change data comes from the SSH command port instead,
    authenticated by the SSH key already registered with Gerrit (the same
    one used for `git push`/`git review`). Confirmed working against Gerrit
    3.12.0 - the `gerrit query` ssh command is long-deprecated upstream but
    still present here.

    Output is JSONL: one JSON object per matching change, plus a trailing
    `{"type": "stats", ...}` summary line that's dropped here.
    """
    require_env(["GERRIT_USER"])
    cmd = [
        "ssh", "-p", GERRIT_SSH_PORT,
        "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
        f"{os.environ['GERRIT_USER']}@{GERRIT_HOST}",
        "gerrit", "query", "--format=JSON",
    ]
    if comments:
        cmd.append("--comments")
    cmd.append(query)

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        die(f"gerrit query over ssh failed: {result.stderr.strip()}")

    changes = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        if obj.get("type") == "stats":
            continue
        changes.append(obj)
    return changes


def ci_auth_header():
    require_env(["CI_USER", "CI_API_TOKEN"])
    return _basic_auth_header(os.environ["CI_USER"], os.environ["CI_API_TOKEN"])


def ci_get_json(url):
    """Raises urllib.error.HTTPError on failure (e.g. a build pruned by
    Jenkins retention that an old Gerrit comment still links to) - the
    caller decides whether that's fatal or just one bad row to skip."""
    req = urllib.request.Request(url.rstrip("/") + "/api/json")
    req.add_header("Authorization", ci_auth_header())
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def ci_get_console_tail(url, max_bytes=MAX_CONSOLE_TAIL):
    """Stream consoleText and keep only the last `max_bytes` (the failure
    summary is always at the end; full bitbake logs can be tens of MB)."""
    req = urllib.request.Request(url.rstrip("/") + "/consoleText")
    req.add_header("Authorization", ci_auth_header())
    tail = b""
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            while True:
                chunk = resp.read(8192)
                if not chunk:
                    break
                tail = (tail + chunk)[-max_bytes:]
    except urllib.error.HTTPError as e:
        die(f"CI request failed ({e.code}) for {url}/consoleText")
    return tail.decode("utf-8", errors="replace")


def ci_fetch_html(url):
    req = urllib.request.Request(url)
    req.add_header("Authorization", ci_auth_header())
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        die(f"CI request failed ({e.code}) for {url}")


def ci_get_crumb(base_url):
    """Best-effort fetch of a Jenkins CSRF crumb; returns (header_name, value) or None."""
    req = urllib.request.Request(base_url.rstrip("/") + "/crumbIssuer/api/json")
    req.add_header("Authorization", ci_auth_header())
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
            return data["crumbRequestField"], data["crumb"]
    except Exception:
        return None
