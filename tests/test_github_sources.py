import json
import unittest
from dataclasses import replace
from github_sources import (SOURCES, select_sources, direct_application_url, parse_simplify,
                            parse_markdown, parse_applyguy, canonical_url)


class GithubFeedsTests(unittest.TestCase):
    def test_sources(self):
        self.assertEqual(len(select_sources("all")), 5)
        self.assertEqual([s.id for s in select_sources("speedy-aiml,simplify")], ["simplify", "speedy-aiml"])
        with self.assertRaises(ValueError):
            select_sources("other")

    def test_urls(self):
        self.assertIsNone(direct_application_url("https://simplify.jobs/p/some"))
        self.assertIsNone(direct_application_url("https://applyguy.ai/jobs?job=abc"))
        self.assertIsNone(direct_application_url("https://company.com/"))
        self.assertIsNone(direct_application_url("https://company.com/careers"))
        self.assertEqual(direct_application_url("https://jobs.lever.co/company/abc/apply"), "https://jobs.lever.co/company/abc/apply")
        self.assertTrue(direct_application_url("https://www.google.com/about/careers/applications/jobs/results/123"))
        self.assertEqual(canonical_url("https://jobs.lever.co/co/id?utm_source=a&x=1"), "https://jobs.lever.co/co/id?x=1")

    def test_simplify_categories_followup_and_aggregators(self):
        text = '''## 💻 Software Engineering New Grad Roles
<table><tr><td><strong><a href="https://simplify.jobs/c/Acme">Acme</a></strong></td><td>New Grad Software Engineer</td><td>Virginia</td><td><a href="https://boards.greenhouse.io/acme/jobs/123"><img alt="Apply"></a> <a href="https://simplify.jobs/p/abc"><img alt="Simplify"></a></td><td>0d</td></tr>
<tr><td>↳</td><td>Junior Engineer</td><td>Remote</td><td><a href="https://jobs.lever.co/acme/456/apply">Apply</a></td><td>1d</td></tr></table>
## 🤖 Data Science, AI & Machine Learning New Grad Roles
<table><tr><td>DataCo</td><td>Data Engineer, New Grad</td><td>NY</td><td><a href="https://jobs.ashbyhq.com/dataco/a1/application">Apply</a></td><td>1d</td></tr></table>'''
        jobs = parse_simplify(text, SOURCES[0])
        self.assertEqual(len(jobs), 3)
        self.assertEqual([j.category for j in jobs], ["SWE", "SWE", "DE"])
        self.assertEqual(jobs[1].company, "Acme")
        self.assertEqual(jobs[0].application_url, "https://boards.greenhouse.io/acme/jobs/123")

    def test_vansh_markdown_uses_apply_column(self):
        text = '''| Company | Role | Location | Application/Link | Date Posted |
| --- | --- | --- | :---: | :---: |
| **Example** | Junior Data Engineer | Remote | <a href="https://job-boards.greenhouse.io/example/jobs/22"><img alt="Apply"></a> | Oct 22 |
| **Other** | ML Engineer | Boston | <a href="https://jobright.ai/jobs/info/xyz">Apply</a> | Oct 22 |
| **Closed** | Engineer | NY | 🔒 | Oct 21 |
'''
        jobs = parse_markdown(text, SOURCES[1])
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].category, "DE")

    def test_speedy_newgrad_not_intern(self):
        text='''## New Graduate Positions
| Company | Position | Location | Salary | Posting | Age |
|---|---|---|---|---|---|
| <a href="https://acme.com"><strong>Acme</strong></a> | ML Engineer - New Grad 2027 | NYC | $120k | <a href="https://jobs.lever.co/acme/987/apply"><img alt="Apply"></a> | 1d |
'''
        jobs=parse_markdown(text,SOURCES[3])
        self.assertEqual(len(jobs),1)
        self.assertEqual(jobs[0].category,"AI/ML")

    def test_applyguy_original_over_aggregator(self):
        payload={"jobs":[{"id":"one","company":"Etsy","title":"Software Engineer I","location":"NYC","url":"https://applyguy.ai/jobs?job=one","listingUrl":"https://etsy.wd5.myworkdayjobs.com/external/job/NYC/SWE_123"},{"company":"Bad","title":"Engineer","url":"https://applyguy.ai/jobs?job=two"}]}
        jobs=parse_applyguy(json.dumps(payload),SOURCES[4])
        self.assertEqual(len(jobs),1)
        self.assertEqual(jobs[0].company,"Etsy")
        self.assertIn('etsy.wd5.myworkdayjobs.com',jobs[0].application_url)

if __name__=='__main__':
    unittest.main()

# Additional tests loaded by unittest discovery under this class.
class MixedClassificationTests(unittest.TestCase):
    def test_exclude_product_and_quant(self):
        text = '''| Company | Role | Location | Application/Link | Date Posted |
| --- | --- | --- | --- | --- |
| **Example** | Product Manager | Seattle | <a href="https://jobs.lever.co/co/pm123">Apply</a> | Oct 22 |
| **Quant** | Quantitative Trader | NY | <a href="https://jobs.lever.co/co/q123">Apply</a> | Oct 22 |
| **Software** | Software Engineer | Remote | <a href="https://jobs.lever.co/co/swe123">Apply</a> | Oct 22 |
'''
        rows = parse_markdown(text, SOURCES[1])
        self.assertEqual([x.role for x in rows], ['Software Engineer'])