#!/usr/bin/env python3
"""Build the full report: open changes -> their CI jobs -> pass/fail/why.

Usage:
    report.py [--query QUERY] --index-file PATH

Prints a human-readable table to stdout, and writes a JSON index file
mapping small integer IDs to build URLs at PATH, so a later retrigger step
can say "retrigger 2 and 5" instead of re-typing/re-deriving URLs.

--index-file is required and should point at this session's scratchpad dir
(the SKILL.md procedure passes it explicitly) - never /tmp.
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(__file__)


def run_json(args):
    out = subprocess.run(
        [sys.executable] + args, capture_output=True, text=True
    )
    if out.returncode != 0:
        print(out.stderr, file=sys.stderr)
        sys.exit(out.returncode)
    return json.loads(out.stdout)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", default="owner:self status:open")
    ap.add_argument("--index-file", required=True)
    args = ap.parse_args()

    changes = run_json(
        [os.path.join(HERE, "list_open_changes.py"), "--query", args.query]
    )["changes"]

    rows = []
    index = {}
    row_id = 1
    for c in changes:
        if not c["jobs"]:
            rows.append(
                {
                    "id": None,
                    "change": c["number"],
                    "subject": c["subject"],
                    "url": c["url"],
                    "job": None,
                    "status": "NO_CI_LINK_FOUND",
                    "detail": "-",
                }
            )
            continue
        for job in c["jobs"]:
            check = run_json([os.path.join(HERE, "check_build.py"), job["url"]])
            status = "RUNNING" if check["building"] else (check["result"] or "UNKNOWN")
            if status == "FAILURE" or (status == "UNSTABLE"):
                detail = check["category"]
                if check.get("recipe"):
                    detail = f"{check['category']} ({check['recipe']}:{check['task']})"
            else:
                detail = "-"
            rid = row_id
            row_id += 1
            index[rid] = {
                "change": c["number"],
                "job": job["job"],
                "build": job["build"],
                "build_url": job["url"],
            }
            rows.append(
                {
                    "id": rid,
                    "change": c["number"],
                    "subject": c["subject"],
                    "url": c["url"],
                    "job": f"{job['job']} #{job['build']}",
                    "status": status,
                    "detail": detail,
                    "console_url": check.get("console_url"),
                    "excerpt": check.get("excerpt"),
                }
            )

    with open(args.index_file, "w") as f:
        json.dump(index, f, indent=2)

    print(f"{'ID':<4}{'Change':<10}{'Job':<38}{'Status':<10}{'Why (if failed)'}")
    for r in rows:
        idstr = str(r["id"]) if r["id"] else "-"
        print(
            f"{idstr:<4}{r['change']:<10}{(r['job'] or '-'):<38}{r['status']:<10}{r['detail']}"
        )
        print(f"     {r['url']}")
        if r.get("console_url") and r["status"] in ("FAILURE", "UNSTABLE"):
            print(f"     console: {r['console_url']}")
        print(f"     {r['subject']}")
    print(f"\nIndex written to {args.index_file} for retrigger.py.")


if __name__ == "__main__":
    main()
