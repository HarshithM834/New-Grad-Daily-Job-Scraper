"""One command to collect six CareerOps sources and sync user-selected outputs.

The three newgrad-jobs.com categories count as one job-board provider;
the other five sources are opt-in-capable community-curated GitHub feeds.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path

from entry_level import select_categories
from github_sources import import_into_tracker, select_sources

LOG = logging.getLogger("careerops")
DEFAULT_TRACKER = Path(__file__).resolve().parent / "2027 New Grad Positions Tracker - Sheet1.csv"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="CareerOps: collect entry-level jobs from six sources")
    parser.add_argument("--csv", type=Path, default=Path(os.environ.get("CAREEROPS_CSV_PATH", DEFAULT_TRACKER)))
    parser.add_argument("--categories", default=os.getenv("CAREEROPS_CATEGORIES", "all"), help="SWE,DE,AI/ML or all")
    parser.add_argument("--community-feeds", default=os.getenv("CAREEROPS_GITHUB_SOURCES", "all"), help="Community feed IDs or all")
    parser.add_argument("--max-jobs-per-source", type=int, default=int(os.getenv("MAX_JOBS_PER_SOURCE", "50")))
    parser.add_argument("--max-per-community", type=int, default=int(os.getenv("MAX_COMMUNITY_JOBS", "150")))
    parser.add_argument("--scroll-steps", type=int, default=int(os.getenv("SCROLL_STEPS", "24")))
    parser.add_argument("--skip-jobright", action="store_true", help="Collect only curated GitHub feeds")
    parser.add_argument("--skip-community", action="store_true", help="Collect only newgrad-jobs.com feeds")
    parser.add_argument("--dry-run", action="store_true", help="Preview community feeds without modifying files; skips browser scraper and exports")
    parser.add_argument("--skip-export", action="store_true", help="Don't send jobs to configured output destinations")
    parser.add_argument("--include-ambiguous", action="store_true", help="Include unclassified roles from the Jobright-backed feed")
    args = parser.parse_args(argv)
    if args.max_jobs_per_source < 1 or args.max_per_community < 1 or args.scroll_steps < 0:
        parser.error("Job limits must be positive; scroll steps must not be negative")
    if args.skip_community and args.skip_jobright:
        parser.error("At least one source must be enabled")
    if args.dry_run and args.skip_community:
        parser.error("Dry-run needs the community sources enabled")
    try:
        args.selected_categories = select_categories(args.categories)
        args.selected_community = select_sources(args.community_feeds)
    except ValueError as exc:
        parser.error(str(exc))
    if not args.csv.is_file():
        parser.error(f"Tracker not found: {args.csv}; start from examples/tracker-template.csv")
    return args


def execute(args) -> dict:
    """Allow source-level failures without discarding jobs from healthy sources."""
    result: dict = {"sources": {}, "errors": {}, "export": None}
    successes = 0
    if not args.skip_community:
        try:
            stats = import_into_tracker(args.csv, args.selected_community,
                                        args.max_per_community, args.selected_categories,
                                        args.dry_run, new_grad_only=True)
            result["sources"]["community"] = stats
            if stats.get("status") == "partial":
                result["errors"].update(stats.get("source_errors", {}))
            successes += stats.get("sources_checked", 0)
        except Exception as exc:
            result["errors"]["community"] = f"{type(exc).__name__}: {exc}"
            LOG.exception("Community source collection failed")
    if not args.skip_jobright and not args.dry_run:
        try:
            from scraper import run
            added = asyncio.run(run(args.csv, args.max_jobs_per_source, args.scroll_steps,
                                    categories=args.selected_categories,
                                    likely_new_grad_only=not args.include_ambiguous))
            result["sources"]["newgrad-jobs"] = {"added": added, "status": "success"}
            successes += 1
        except Exception as exc:
            result["errors"]["newgrad-jobs"] = f"{type(exc).__name__}: {exc}"
            LOG.exception("newgrad-jobs.com scraper failed")
    if successes and not args.dry_run and not args.skip_export:
        try:
            from output_connectors import export_all
            # Connectors are user-configured. Default CSV is local and requires no secrets.
            result["export"] = export_all(csv_path=args.csv,
                config_path=args.csv.parent / "destinations.local.json")
            for item in result["export"].get("results", []):
                if item.get("status") == "failed":
                    result["errors"][f"output:{item.get('type', 'unknown')}"] = str(item.get("error", "failed"))[:180]
        except Exception as exc:
            result["errors"]["outputs"] = f"{type(exc).__name__}: {exc}"
            LOG.exception("Destination synchronization failed")
    result["status"] = "failed" if successes == 0 else "partial" if result["errors"] else "success"
    return result


def main(argv=None):
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = execute(args)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())