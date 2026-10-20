#!/usr/bin/env python3
"""List open Gerrit changes and the CI job links found in their comments.

Usage:
    list_open_changes.py [--query QUERY]

QUERY defaults to "owner:self status:open" (the changes you'd actually want
to retrigger). Pass e.g. --query "status:open" to include changes you're
only reviewing.

Prints one JSON object to stdout:
{
  "changes": [
    {
      "number": 111971,
      "subject": "...",
      "project": "Supervyse-OPF/bmcweb-override",
      "branch": "...",
      "url": "https://gerrit.insyde.com/c/<project>/+/<number>",
      "jobs": [
        {"job": "BMC_OPF2.0-GB300_CEC173X-pfr", "build": 2346,
         "url": "https://bema.insyde.com/job/BMC_OPF2.0-GB300_CEC173X-pfr/2346"}
      ]
    },
    ...
  ]
}

How a change's CI job is found: the Gerrit Trigger plugin posts a comment
("Jenkins_Verify") on the change containing a link to each Jenkins build it
started, e.g. ".../job/<name>/<build>/". This script scans every comment's
text for such links and, per job name, keeps the highest build number seen
(the most recent run) - confirmed against real changes in
Supervyse-OPF/bmcweb-override.

Change data comes from `gerrit query` over ssh (see _common.py
gerrit_ssh_query) rather than the REST API, since this Gerrit account has
no HTTP Credentials to authenticate REST calls with.
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _common import gerrit_ssh_query, CI_URL_HOST_DEFAULT  # noqa: E402
import json  # noqa: E402

CI_HOST = os.environ.get("CI_URL_HOST", CI_URL_HOST_DEFAULT)
JOB_LINK_RE = re.compile(
    r"https?://" + re.escape(CI_HOST) + r"/job/([\w.\-]+)/(\d+)/?"
)


def extract_jobs(comments):
    best = {}  # job name -> build number
    for c in comments:
        for job, build in JOB_LINK_RE.findall(c.get("message", "")):
            build = int(build)
            if job not in best or build > best[job]:
                best[job] = build
    return [
        {"job": job, "build": build, "url": f"https://{CI_HOST}/job/{job}/{build}"}
        for job, build in sorted(best.items())
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", default="owner:self status:open")
    args = ap.parse_args()

    data = gerrit_ssh_query(args.query, comments=True)
    changes = []
    for c in data:
        changes.append(
            {
                "number": c["number"],
                "subject": c.get("subject", ""),
                "project": c["project"],
                "branch": c.get("branch", ""),
                "url": c["url"],
                "jobs": extract_jobs(c.get("comments", [])),
            }
        )
    print(json.dumps({"changes": changes}, indent=2))


if __name__ == "__main__":
    main()
