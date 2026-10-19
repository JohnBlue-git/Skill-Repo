#!/usr/bin/env python3
"""One-off diagnostic: find the actual "Retrigger" link on a build page.

retrigger.py already POSTs to the confirmed real endpoint
(<build_url>/gerrit-trigger-retrigger-this/index, verified against
bema.insyde.com by capturing an actual browser click in DevTools) - you
shouldn't need this script there. It's kept for the case a *different*
CI instance/job type turns out to expose the button differently.

Note it will find nothing on a modern Jenkins "two-column" UI (2.4xx+):
those render sidebar action buttons via JS from the build's `actions` API,
not as static <a href> HTML, so simple scraping can't see them - capturing
the real click in browser DevTools (Network tab) is the reliable fallback.

Usage:
    discover_retrigger.py <build_url>

Prints any hrefs on the page containing "retrigger" or "reverify"
(case-insensitive), plus their surrounding link text.
"""
import re
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from _common import ci_fetch_html  # noqa: E402

LINK_RE = re.compile(r'<a[^>]+href="([^"]*)"[^>]*>([^<]*)</a>', re.IGNORECASE)


def main():
    if len(sys.argv) != 2:
        print("usage: discover_retrigger.py <build_url>", file=sys.stderr)
        sys.exit(2)
    build_url = sys.argv[1].rstrip("/")
    html = ci_fetch_html(build_url + "/")

    found = [
        (href, text.strip())
        for href, text in LINK_RE.findall(html)
        if "retrigger" in href.lower() or "reverify" in href.lower()
        or "retrigger" in text.lower() or "reverify" in text.lower()
    ]

    if not found:
        print(
            "No retrigger/reverify-looking links found on the page.\n"
            "Either this build wasn't Gerrit-triggered, you lack permission to "
            "see the action, or the CI names it something else - open the build "
            "page in a browser and inspect the button manually."
        )
        return

    print(f"Candidate links on {build_url}/:")
    for href, text in found:
        resolved = href if href.startswith("http") else build_url + "/" + href.lstrip("/")
        print(f"  text={text!r} href={href!r} -> {resolved}")


if __name__ == "__main__":
    main()
