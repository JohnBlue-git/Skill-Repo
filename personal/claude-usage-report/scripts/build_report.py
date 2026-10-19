#!/usr/bin/env python3
"""Build the self-contained usage-report HTML from local Claude Code logs.

Usage:
    python3 build_report.py [output.html]

With no argument, writes the HTML to stdout and a summary to stderr.
"""
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from parse_usage import compute_usage  # noqa: E402

TEMPLATE_PATH = os.path.join(SCRIPT_DIR, "..", "templates", "usage_report.html")


def build(out_path=None):
    result = compute_usage()
    daily = result["daily"]

    with open(TEMPLATE_PATH) as f:
        html = f.read()
    html = html.replace("__DAILY_DATA__", json.dumps(daily))

    if out_path:
        with open(out_path, "w") as f:
            f.write(html)
    else:
        sys.stdout.write(html)

    total_cost = sum(d["cost_usd"] for d in daily.values())
    dest = f" -> written to {out_path}" if out_path else ""
    print(
        f"[build_report] {result['files_scanned']} files scanned, {len(daily)} active days, "
        f"${total_cost:.2f} estimated{dest}",
        file=sys.stderr,
    )
    return daily


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else None)
