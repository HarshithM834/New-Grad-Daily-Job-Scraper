import json
import unittest
from unittest.mock import patch

from feed_health import FEEDS, parse_feed, main


def document(category="swe", n=2, total=100):
    payload={"props":{"pageProps":{"pathInfo":{"category":category},"initialTotal":total,
      "initialJobs":[{"id":str(i),"company":"Example Corp","title":f"Junior Engineer {i}","isNewGrad":i==0} for i in range(n)]}}}
    return '<html><script id="__NEXT_DATA__" type="application/json">'+json.dumps(payload)+'</script></html>'


class FeedContractTests(unittest.TestCase):
    def test_reports_first_page_and_not_full_archive(self):
        r=parse_feed(document(),"swe")
        self.assertEqual(r["reported_total"],100)
        self.assertEqual(r["initial_visible"],2)
        self.assertTrue(r["needs_pagination"])
        self.assertEqual(r["newgrad_flagged"],1)

    def test_different_category_is_error(self):
        with self.assertRaisesRegex(ValueError,"Expected category"):
            parse_feed(document("ml_ai"),"swe")

    def test_empty_feed_is_failure(self):
        with self.assertRaisesRegex(ValueError,"empty initialJobs"):
            parse_feed(document(n=0),"swe")

    def test_missing_next_data_is_failure(self):
        with self.assertRaisesRegex(ValueError,"Missing Next.js"):
            parse_feed("<html><body>blocked</body></html>","swe")

    def test_unexpected_job_schema_is_failure(self):
        h=document().replace('"company": "Example Corp"', '"employer": "Example Corp"')
        with self.assertRaisesRegex(ValueError,"lacks id"):
            parse_feed(h,"swe")

    def test_main_reports_all_three_categories(self):
        with patch('feed_health.probe',side_effect=lambda u,c,t: parse_feed(document(c),c)):
            self.assertEqual(main(['--json']),0)

    def test_main_detects_failed_source(self):
        def fake(url,cat,timeout):
            if cat=='ml_ai':raise ValueError('feed unavailable')
            return parse_feed(document(cat),cat)
        with patch('feed_health.probe',side_effect=fake):
            self.assertEqual(main(['--json']),1)

    def test_feeds_cover_three_expected_categories(self):
        self.assertEqual([f[1] for f in FEEDS],['swe','data_engineer','ml_ai'])

if __name__=='__main__':unittest.main()