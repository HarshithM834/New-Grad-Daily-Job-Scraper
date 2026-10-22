import csv
import json
import unittest
from unittest.mock import AsyncMock, patch
from pathlib import Path
from tempfile import TemporaryDirectory
from scraper import (COLUMNS, SOURCES, Job, collect_all_jobs, extract_jobs, extract_next_data, employer_url, merge_rows,
                     normalized_url, read_tracker, write_csv_atomic)


class ScraperTests(unittest.TestCase):
    def test_next_data_rows(self):
        doc = {"props": {"pageProps": {"initialJobs": [
            {"id": "abc", "title": "Graduate SWE", "company": "Example",
             "location": "Herndon, VA", "applyUrl": "https://jobright.ai/jobs/info/abc"}
        ]}}}
        html = '<script id="__NEXT_DATA__" type="application/json">' + json.dumps(doc) + '</script>'
        jobs = extract_next_data(html)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].job_id, "abc")

    def test_provider_url_filter(self):
        self.assertIsNone(employer_url("https://jobright.ai/jobs/info/abc"))
        self.assertIsNone(employer_url("https://www.indeed.com/viewjob?jk=123"))
        self.assertEqual(employer_url("https://boards.greenhouse.io/acme/jobs/123"),
                         "https://boards.greenhouse.io/acme/jobs/123")

    def test_preserve_existing_stage_and_no_duplicate(self):
        a = {"Company": "ACME", "Role": "SWE I", "Link": "https://acme.com/job1",
             "Location": "Virginia", "Stage": "Applied", "To-do": "No", "Notes": "Interview booked"}
        j1 = Job("x", "ACME", "SWE I", "Virginia", "https://jobright.ai/jobs/info/x")
        j2 = Job("y", "Other", "Graduate SWE", "Maryland", "https://jobright.ai/jobs/info/y")
        rows, count = merge_rows([a], [(j1, "https://acme.com/job1"),
                                       (j2, "https://boards.greenhouse.io/other/jobs/123")])
        self.assertEqual(count, 1)
        self.assertEqual(rows[0], a)
        self.assertEqual(rows[1]["Stage"], "Not Applied")
        self.assertEqual(rows[1]["To-do"], "Yes")

    def test_csv_roundtrip(self):
        with TemporaryDirectory() as d:
            p = Path(d) / "jobs.csv"
            row = dict.fromkeys(COLUMNS, "")
            row.update({"Company": "M&M", "Role": "Software Engineer", "Notes": "note,comma"})
            write_csv_atomic(p, [row])
            self.assertEqual(read_tracker(p), [row])

    def test_no_formula_injection(self):
        obj = {"id":"1", "title":"=HYPERLINK('bad')", "company":"@BAD",
               "location":"Anywhere"}
        j = extract_jobs(obj)[0]
        self.assertTrue(j.role.startswith("'="))
        self.assertTrue(j.company.startswith("'@"))

    def test_strip_tracking_parameters(self):
        self.assertEqual(normalized_url("https://company.com/jobs/123?utm_source=abc&ref=jobright"),
                         "https://company.com/jobs/123")



class FeedTests(unittest.IsolatedAsyncioTestCase):
    async def test_three_feed_urls_and_actual_embed_paths(self):
        self.assertEqual([s.page_url for s in SOURCES], [
            "https://www.newgrad-jobs.com/?k=swe",
            "https://www.newgrad-jobs.com/?k=de",
            "https://www.newgrad-jobs.com/?k=aiml",
        ])
        self.assertEqual([s.embed_url.split("?")[0].split("/us/")[-1] for s in SOURCES],
                         ["swe", "data_engineer", "ml_ai"])

    async def test_merge_three_feeds_and_deduplicate_shared_job(self):
        def fake_collect(context, *, source, max_jobs, scroll_steps):
            self.assertEqual(max_jobs, 7)
            self.assertEqual(scroll_steps, 4)
            common = Job("common", "Company", "Engineer", "US", "https://jobright.ai/jobs/info/common")
            unique = Job(source.category, source.category, "Engineer", "Remote", "https://jobright.ai/jobs/info/"+source.category)
            return [common, unique]
        with patch("scraper.collect_jobs", new=AsyncMock(side_effect=fake_collect)) as mock:
            jobs = await collect_all_jobs(object(), max_jobs_per_source=7, scroll_steps=4)
        self.assertEqual(mock.await_count, 3)
        self.assertEqual([j.job_id for j in jobs], ["common", "SWE", "DE", "AI/ML"])

    async def test_feed_failure_is_not_silenced(self):
        with patch("scraper.collect_jobs", new=AsyncMock(side_effect=RuntimeError("feed down"))):
            with self.assertRaisesRegex(RuntimeError, "feed down"):
                await collect_all_jobs(object(), max_jobs_per_source=5, scroll_steps=2)

if __name__ == "__main__":
    unittest.main()