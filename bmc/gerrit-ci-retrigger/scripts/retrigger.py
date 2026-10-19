#!/usr/bin/env python3
"""Fire the CI "Retrigger" action for one or more build URLs.

Usage:
    retrigger.py [--dry-run] <build_url> [build_url ...]
    retrigger.py [--dry-run] --index-file PATH --ids 2,5

The second form looks up build URLs by the small integer IDs report.py
printed and wrote to PATH - use it instead of retyping/re-deriving URLs.

For each build URL (e.g. https://bema.insyde.com/job/<name>/<number>), POSTs
to <build_url>/gerrit-trigger-retrigger-this/index - the real endpoint the
Gerrit Trigger plugin's "Retrigger" button calls, confirmed by capturing an
actual browser click in DevTools (POST, 302 on success). A CSRF crumb is
attached if the instance's /crumbIssuer is enabled; omitted if not.

--dry-run prints exactly what would be requested without sending anything.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))
from _common import ci_auth_header, ci_get_crumb  # noqa: E402

RETRIGGER_SUFFIX = "gerrit-trigger-retrigger-this/index"


def try_post(url, crumb):
    req = urllib.request.Request(url, method="POST", data=b"")
    req.add_header("Authorization", ci_auth_header())
    if crumb:
        req.add_header(crumb[0], crumb[1])
    return urllib.request.urlopen(req, timeout=30)


def retrigger_one(build_url, dry_run):
    url = build_url.rstrip("/") + "/" + RETRIGGER_SUFFIX
    if dry_run:
        print(f"[dry-run] would POST {url}")
        return True

    base = build_url.split("/job/", 1)[0]
    crumb = ci_get_crumb(base)
    try:
        try_post(url, crumb)
        print(f"OK  (POST) {url}")
        return True
    except urllib.error.HTTPError as e:
        print(f"FAIL (POST {e.code}) {url}")
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--index-file")
    ap.add_argument("--ids", help="comma-separated IDs from report.py's table")
    ap.add_argument("build_urls", nargs="*")
    args = ap.parse_args()

    urls = list(args.build_urls)
    if args.ids:
        if not args.index_file:
            print("--ids requires --index-file", file=sys.stderr)
            sys.exit(2)
        with open(args.index_file) as f:
            index = json.load(f)
        for rid in args.ids.split(","):
            entry = index.get(rid.strip())
            if not entry:
                print(f"no such ID in index: {rid}", file=sys.stderr)
                sys.exit(2)
            urls.append(entry["build_url"])

    if not urls:
        print("no build URLs given (pass them directly or via --index-file/--ids)", file=sys.stderr)
        sys.exit(2)

    results = [retrigger_one(u, args.dry_run) for u in urls]
    if not all(results):
        sys.exit(1)


if __name__ == "__main__":
    main()
