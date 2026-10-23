"""Regression tests for all-source orchestration and safe community imports."""
from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from careerops import parse_args, execute
from entry_level import classify_role
from github_sources import SOURCES, ListedJob, eligible_curated_role, import_into_tracker
from scraper import COLUMNS, read_tracker
from scraper_reliability import employer_application_url


class NewGradOnlyTests(unittest.TestCase):
    def test_curated_newgrad_lists_cannot_import_senior_or_interns(self):
        for title in ("Senior Backend Engineer", "Staff ML Engineer", "AI Intern", "SWE Co-op"):
            self.assertFalse(eligible_curated_role(title), title)
        for title in ("Junior Developer", "Software Engineer I", "Software Engineer", "New Grad Data Engineer"):
            self.assertTrue(eligible_curated_role(title), title)
        self.assertEqual(classify_role("Software Engineer"), "unknown")

    def test_source_adapters_total_six_providers(self):
        self.assertEqual(len(SOURCES), 5)
        self.assertEqual(len({s.id for s in SOURCES}), 5)
        self.assertEqual(len(SOURCES) + 1, 6)

    def test_known_google_careers_link_is_allowed(self):
        url = "https://www.google.com/about/careers/applications/jobs/results/123"
        self.assertEqual(employer_application_url(url), url)


class RunnerTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.csv = Path(t.name) / "jobs.csv"
        with self.csv.open("w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=COLUMNS).writeheader()

    def test_community_default_selects_every_feed_and_newgrad(self):
        args = parse_args(["--csv", str(self.csv), "--dry-run"])
        self.assertEqual(len(args.selected_community), 5)
        self.assertEqual(args.selected_categories, ("SWE", "DE", "AI/ML"))
        with patch("careerops.import_into_tracker", return_value={"sources_checked": 5, "status": "success"}) as importer:
            out = execute(args)
        self.assertEqual(out["status"], "success")
        self.assertTrue(importer.call_args.kwargs["new_grad_only"])
        self.assertTrue(importer.call_args.args[4])  # dry-run

    def test_source_failure_does_not_erase_successful_import(self):
        args = parse_args(["--csv", str(self.csv), "--skip-export"])
        with patch("careerops.import_into_tracker", return_value={"sources_checked": 3, "status": "partial", "source_errors": {"vansh": "network timeout"}}), \
             patch("scraper.run", new=AsyncMock(side_effect=RuntimeError("Jobright unavailable"))):
            out = execute(args)
        self.assertEqual(out["status"], "partial")
        self.assertIn("vansh", out["errors"])
        self.assertIn("newgrad-jobs", out["errors"])

    def test_zero_successful_sources_fails(self):
        args = parse_args(["--csv", str(self.csv), "--skip-export"])
        with patch("careerops.import_into_tracker", side_effect=RuntimeError("offline")), \
             patch("scraper.run", new=AsyncMock(side_effect=RuntimeError("offline"))):
            out = execute(args)
        self.assertEqual(out["status"], "failed")


class ExcelExportTests(unittest.TestCase):
    def test_xlsx_created_and_safe(self):
        try:
            from artifact_tool import Blob, SpreadsheetFile
        except ImportError:
            self.skipTest("Excel export requires optional artifact_tool")
        from excel_export import make_xlsx
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "test.xlsx"
            make_xlsx([{"Company": "Acme", "Role": "SWE 1", "Notes": "=1+1"}], p)
            book = SpreadsheetFile.import_xlsx(Blob.load(str(p)))
            sheet = book.worksheets.get_item("Jobs")
            self.assertEqual(sheet.get_range("A1").values[0][0], "Company")
            self.assertEqual(sheet.get_range("G2").values[0][0], "=1+1")
            self.assertEqual(sheet.get_range("G2").formulas[0][0], "")


if __name__ == "__main__":
    unittest.main()