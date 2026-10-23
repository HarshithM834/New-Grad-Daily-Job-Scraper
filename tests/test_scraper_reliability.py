import csv
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from scraper_reliability import employer_application_url, update_unresolved_queue


@dataclass
class Job:
    job_id: str
    company: str
    role: str
    location: str
    source_url: str
    category: str = 'SWE'


class EmployerApplicationURLTests(unittest.TestCase):
    def test_accept_real_ats_links(self):
        examples = [
            'https://boards.greenhouse.io/acme/jobs/1234567',
            'https://jobs.lever.co/company/engineer-9a5f5a',
            'https://jobs.ashbyhq.com/example/abc-def',
            'https://example.wd5.myworkdayjobs.com/en-US/External/job/Palo-Alto/Engineer_R1234',
            'https://jobs.example.com/1',
            'https://company.com/careers?jobId=123',
        ]
        for u in examples:
            with self.subTest(u=u):
                self.assertEqual(employer_application_url(u), u)

    def test_reject_aggregators_and_homepages(self):
        examples = [
            'https://jobright.ai/jobs/info/abc', 'https://sub.jobright.ai/jobs/info/abc',
            'https://linkedin.com/jobs/view/123', 'https://indeed.com/viewjob?id=10',
            'https://company.com/', 'https://company.com/careers',
            'https://company.com/jobs', 'https://company.com/search',
            'https://company.com/login?redirect=/jobs/2',
            'https://company.com/redirect?to=https%3A%2F%2Fjobs.company.com%2F1',
            'https://127.0.0.1/job/123', 'http://10.0.0.1/job/123',
            'http://localhost:8000/job/123', 'http://a.internal/job/123',
            'javascript:alert(1)', 'https://user:password@company.com/jobs/1',
            'https://company.com:4443/jobs/1', 'not a url',
        ]
        for u in examples:
            with self.subTest(u=u):
                self.assertIsNone(employer_application_url(u))

    def test_remove_fragment(self):
        self.assertEqual(employer_application_url('https://jobs.example.com/open/1#token'),
                         'https://jobs.example.com/open/1')


class UnresolvedQueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.queue = Path(self.tmp.name) / 'unresolved_jobs.csv'
        self.a = Job('a', 'A Corp', 'Engineer', 'Remote', 'https://jobright.ai/jobs/info/a?utm_id=1')
        self.b = Job('b', 'B Corp', 'Data Engineer', 'VA', 'https://jobright.ai/jobs/info/b', 'DE')

    def rows(self):
        with self.queue.open(encoding='utf-8-sig', newline='') as fh:
            return list(csv.DictReader(fh))

    def test_persist_increment_and_remove(self):
        self.assertEqual(update_unresolved_queue(self.queue, [self.a], now='2026-10-22T10:00:00Z'), 1)
        self.assertEqual(update_unresolved_queue(self.queue, [self.a, self.b], now='2026-10-23T10:00:00Z'), 2)
        rows = self.rows()
        self.assertEqual(rows[0]['Attempts'], '2')
        self.assertEqual(rows[0]['First Seen'], '2026-10-22T10:00:00Z')
        self.assertEqual(rows[0]['Last Seen'], '2026-10-23T10:00:00Z')
        self.assertEqual(update_unresolved_queue(self.queue, [], resolved=[self.a], now='2026-10-24T10:00:00Z'), 1)
        self.assertEqual(self.rows()[0]['Company'], 'B Corp')

    def test_import_existing_legacy_queue(self):
        self.queue.write_text('Category,Company,Role,Location,Jobright Source (review only)\nSWE,A Corp,Engineer,Remote,https://jobright.ai/jobs/info/a\n')
        self.assertEqual(update_unresolved_queue(self.queue, [self.a]), 1)
        self.assertEqual(self.rows()[0]['Attempts'], '2')
        self.assertEqual(len(self.rows()), 1)

    def test_keep_unseen_old_items(self):
        update_unresolved_queue(self.queue, [self.a])
        update_unresolved_queue(self.queue, [self.b])
        self.assertEqual(len(self.rows()), 2)


if __name__ == '__main__':
    unittest.main()

class AdditionalProtectionTests(unittest.TestCase):
    def test_reject_promotional_redirects(self):
        for url in (
            "https://simplify.jobs/p/abc", "https://applyguy.ai/jobs?job=abc",
            "https://speedyapply.com/click/j/123", "https://company.com/careers",
            "https://subdomain.jobright.ai/jobs/info/abc",
        ):
            self.assertIsNone(employer_application_url(url))

    def test_careers_with_specific_job_ids(self):
        self.assertEqual(employer_application_url("https://company.com/careers?jobId=2027"),
                         "https://company.com/careers?jobId=2027")