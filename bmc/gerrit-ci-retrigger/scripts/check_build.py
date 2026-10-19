#!/usr/bin/env python3
"""Fetch one Jenkins build's status and, if it failed, classify why.

Usage:
    check_build.py <build_url>

<build_url> looks like https://bema.insyde.com/job/<name>/<number>

Prints one JSON object to stdout:
{
  "url": "...",
  "building": false,
  "result": "FAILURE",           # SUCCESS | FAILURE | UNSTABLE | ABORTED | null
  "category": "recipe_build_fail",  # bmcweb_build_fail | recipe_build_fail |
                                     # conflict | other | null (null = not failed)
  "recipe": "bmcweb",
  "task": "do_compile",
  "excerpt": "...",              # a few lines of console log context
  "console_url": ".../consoleText",
  "retrigger_url_guess": ".../retrigger"
}

Classification is regex-based over the tail of the console log (see
DESIGN.md "Error classification" for the exact rules and their rationale).
It is a best-effort triage, not a guarantee - always keep the console_url
handy so the human can look when "other" isn't good enough.
"""
import json
import re
import sys
import os
import urllib.error

sys.path.insert(0, os.path.dirname(__file__))
from _common import ci_get_json, ci_get_console_tail  # noqa: E402

CONFLICT_PATTERNS = [
    r"CONFLICT \(",
    r"Automatic merge failed",
    r"error: failed to push",
    r"Merge conflict in",
    r"cannot fast-forward",
    r"repo sync.*failed",
    r"error: Your local changes to the following files would be overwritten",
    r"needs merge",
]

# Standard Yocto/bitbake failure log path:
#   .../work/<arch>/<recipe>/<version>/temp/log.do_<task>.<pid>
RECIPE_LOG_RE = re.compile(
    r"/work/[^/\s]+/(?P<recipe>[^/\s]+)/(?P<version>[^/\s]+)/temp/log\.(?P<task>do_\w+)\.\d+"
)


def classify(console_tail):
    for pat in CONFLICT_PATTERNS:
        if re.search(pat, console_tail, re.IGNORECASE):
            return {"category": "conflict", "recipe": None, "task": None}

    matches = list(RECIPE_LOG_RE.finditer(console_tail))
    if matches:
        m = matches[-1]  # last match = nearest the end = the actual root cause
        recipe = m.group("recipe")
        task = m.group("task")
        category = "bmcweb_build_fail" if "bmcweb" in recipe.lower() else "recipe_build_fail"
        return {"category": category, "recipe": recipe, "task": task}

    return {"category": "other", "recipe": None, "task": None}


def excerpt_of(console_tail, lines=25):
    non_blank = [l for l in console_tail.splitlines() if l.strip()]
    return "\n".join(non_blank[-lines:])


def main():
    if len(sys.argv) != 2:
        print("usage: check_build.py <build_url>", file=sys.stderr)
        sys.exit(2)
    build_url = sys.argv[1].rstrip("/")

    try:
        info = ci_get_json(build_url)
    except urllib.error.HTTPError as e:
        print(json.dumps({
            "url": build_url,
            "building": False,
            "result": "NOT_FOUND" if e.code == 404 else f"CI_ERROR_{e.code}",
            "category": None,
            "recipe": None,
            "task": None,
            "excerpt": None,
            "console_url": build_url + "/consoleText",
            "retrigger_url_guess": build_url + "/retrigger",
        }, indent=2))
        return

    out = {
        "url": build_url,
        "building": info.get("building", False),
        "result": info.get("result"),
        "category": None,
        "recipe": None,
        "task": None,
        "excerpt": None,
        "console_url": build_url + "/consoleText",
        "retrigger_url_guess": build_url + "/retrigger",
    }

    if out["building"]:
        print(json.dumps(out, indent=2))
        return

    if info.get("result") not in (None, "SUCCESS"):
        tail = ci_get_console_tail(build_url)
        out.update(classify(tail))
        out["excerpt"] = excerpt_of(tail)

    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
