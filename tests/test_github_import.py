"""Offline regression tests for importer orchestration using an isolated tracker stub."""
import csv
import sys
import tempfile
import types
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

from github_sources import ListedJob, SOURCES, import_into_tracker


@dataclass(frozen=True)
class FakeJob:
    job_id: str
    company: str
    role: str
    location: str
    source_url: str
    category: str = ""


def make_scraper_stub():
    fake = types.ModuleType("scraper")
    fake.Job = FakeJob
    def read(path):
        with Path(path).open(encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))
    fake.read_tracker = read
    def merge(rows, candidates):
        out = list(rows)
        seen = {row["Link"] for row in out}
        for job, link in candidates:
            if link not in seen:
                out.append(dict(Company=job.company, Role=job.role, Link=link,
                                Location=job.location, Stage="Not Applied", **{"To-do": "Yes"}, Notes=""))
                seen.add(link)
        return out, len(out) - len(rows)
    fake.merge_rows = merge
    def write(path, rows):
        with Path(path).open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=["Company", "Role", "Link", "Location", "Stage", "To-do", "Notes"])
            writer.writeheader()
            writer.writerows(rows)
    fake.write_csv_atomic = write
    fake.record_metadata = lambda *args: None
    fake.record_run = lambda folder, stats: None
    return fake


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.tracker = Path(self.temp.name) / "jobs.csv"
        self.stub = make_scraper_stub()
        self.stub.write_csv_atomic(self.tracker, [dict(Company="OldCo", Role="Engineer", Link="https://jobs.lever.co/old/12", Location="VA", Stage="Interview", **{"To-do": "No"}, Notes="Keep me")])

    def test_partial_source_failure_preserves_notes_and_adds_known_links(self):
        one = ListedJob("Acme", "Graduate SWE", "Boston", "https://jobs.lever.co/acme/abc", "simplify", "SWE", "https://github.com/SimplifyJobs/New-Grad-Positions")
        def fetch(src):
            if src.id == "vansh":
                raise RuntimeError("offline")
            return [one, one]
        with patch.dict(sys.modules, {"scraper": self.stub}), patch("github_sources.fetch_source", side_effect=fetch):
            stats = import_into_tracker(self.tracker, (SOURCES[0], SOURCES[1]), 50, ("SWE",))
        self.assertEqual(stats["status"], "partial")
        self.assertIn("vansh", stats["source_errors"])
        self.assertEqual(stats["added"], 1)
        rows = self.stub.read_tracker(self.tracker)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["Stage"], "Interview")
        self.assertEqual(rows[0]["Notes"], "Keep me")

    def test_dry_run_never_changes_tracker(self):
        before = self.tracker.read_bytes()
        one = ListedJob("Acme", "Graduate SWE", "Boston", "https://jobs.lever.co/acme/abc", "simplify", "SWE", "https://github.com/SimplifyJobs/New-Grad-Positions")
        with patch.dict(sys.modules, {"scraper": self.stub}), patch("github_sources.fetch_source", return_value=[one]):
            stats = import_into_tracker(self.tracker, (SOURCES[0],), 50, dry_run=True)
        self.assertEqual(stats["would_add"], 1)
        self.assertEqual(stats["added"], 0)
        self.assertEqual(self.tracker.read_bytes(), before)

    def test_all_failed_sources_leave_tracker_untouched(self):
        before = self.tracker.read_bytes()
        with patch.dict(sys.modules, {"scraper": self.stub}), patch("github_sources.fetch_source", side_effect=RuntimeError("offline")):
            with self.assertRaisesRegex(RuntimeError, "All selected GitHub feeds failed"):
                import_into_tracker(self.tracker, (SOURCES[0], SOURCES[1]), 10)
        self.assertEqual(before, self.tracker.read_bytes())


if __name__ == "__main__":
    unittest.main()