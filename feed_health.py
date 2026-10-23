"""Live contract check for newgrad-jobs.com's embedded SSR job feeds.

This is intentionally read-only: it never visits Apply Now or writes to a
user's job tracker. A successful probe confirms an HTTP feed contract, not
successful employer-link resolution or the full scraping pipeline.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from html import unescape
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

FEEDS = (
    ("SWE", "swe", "https://jobright.ai/minisites-jobs/newgrad/us/swe?embed=true"),
    ("DE", "data_engineer", "https://jobright.ai/minisites-jobs/newgrad/us/data_engineer?embed=true"),
    ("AI/ML", "ml_ai", "https://jobright.ai/minisites-jobs/newgrad/us/ml_ai?embed=true"),
)
SCRIPT = re.compile(r'<script\b[^>]*\bid=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', re.I | re.S)
USER_AGENT = "CareerOps/0.2 (feed contract check; read-only)"


def parse_feed(html: str, expected_category: str) -> dict:
    """Validate the feed response without silently interpreting empty jobs as success."""
    match = SCRIPT.search(html)
    if not match:
        raise ValueError("Missing Next.js __NEXT_DATA__ payload")
    try:
        obj = json.loads(unescape(match.group(1)))
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid JSON in __NEXT_DATA__") from exc
    props = obj.get("props", {}).get("pageProps", {})
    jobs = props.get("initialJobs")
    total = props.get("initialTotal")
    category = props.get("pathInfo", {}).get("category")
    if category != expected_category:
        raise ValueError(f"Expected category {expected_category}, got {category!r}")
    if not isinstance(jobs, list) or not jobs:
        raise ValueError("Missing or empty initialJobs; the source contract may have changed")
    if not isinstance(total, int) or total < len(jobs):
        raise ValueError("initialTotal is missing or smaller than initialJobs")
    if not all(isinstance(j, dict) and all(isinstance(j.get(x), str) and j[x] for x in ("id", "title", "company")) for j in jobs):
        raise ValueError("At least one listing lacks id, title, or company")
    declared = sum(j.get("isNewGrad") is True for j in jobs)
    return {
        "reported_total": total,
        "initial_visible": len(jobs),
        "category": category,
        "newgrad_flagged": declared,
        "needs_pagination": total > len(jobs),
        "example_role": jobs[0]["title"],
    }


def probe(url: str, category: str, timeout: float = 25.0) -> dict:
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    with urlopen(req, timeout=timeout) as response:
        html = response.read(8_000_000).decode("utf-8", errors="replace")
    return parse_feed(html, category)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only contract check of SWE, DE and AI/ML feeds")
    parser.add_argument("--timeout", type=float, default=25.0)
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    opts = parser.parse_args(argv)
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "feeds": {}, "all_healthy": True,
              "note": "Contract check only; does not verify pagination or employer application links"}
    for label, category, url in FEEDS:
        try:
            item = probe(url, category, opts.timeout)
            report["feeds"][label] = {"status": "healthy", **item}
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            report["feeds"][label] = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"[:280]}
            report["all_healthy"] = False
    if opts.json:
        print(json.dumps(report, indent=2))
    else:
        for label, entry in report["feeds"].items():
            if entry["status"] == "healthy":
                print(f"{label:5s} | OK | {entry['initial_visible']} initial of {entry['reported_total']} reported | newgrad flags: {entry['newgrad_flagged']}")
            else:
                print(f"{label:5s} | FAILED | {entry['error']}")
        print(report["note"])
    return 0 if report["all_healthy"] else 1


if __name__ == "__main__":
    sys.exit(main())