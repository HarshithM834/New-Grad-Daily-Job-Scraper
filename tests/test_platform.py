"""Local/offline regression tests for dashboard and modular output connectors."""
import csv
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dashboard_server import HEADERS, load_state, row_id, update_job
from output_connectors import (DestinationError, config_template, export_all,
                               load_config, make_pdf, public_config, save_config,
                               validate_webhook_url)
from scraper import Job, record_metadata, record_run


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.tracker = self.path / "tracker.csv"
        self.rows = [{"Company": "Example Co", "Role": "Backend Engineer", "Link": "https://jobs.example.com/1",
                      "Location": "Virginia", "Stage": "Applied", "To-do": "Yes", "Notes": "Existing note"}]
        with self.tracker.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=HEADERS)
            writer.writeheader()
            writer.writerows(self.rows)

    def test_update_preserves_columns_and_changes_only_selected_row(self):
        updated = update_job(row_id(self.rows[0]), {"stage": "Interview", "todo": False, "notes": "Phone screen"}, self.tracker)
        self.assertEqual(updated["stage"], "Interview")
        with self.tracker.open(encoding="utf-8-sig", newline="") as stream:
            after = list(csv.DictReader(stream))
        self.assertEqual(len(after), 1)
        self.assertEqual(after[0]["Role"], "Backend Engineer")
        self.assertEqual(after[0]["Stage"], "Interview")
        self.assertEqual(after[0]["To-do"], "No")
        self.assertEqual(after[0]["Notes"], "Phone screen")

    def test_formula_injection_defended(self):
        update_job(row_id(self.rows[0]), {"stage": "Applied", "todo": True, "notes": "=HYPERLINK(\"bad\")"}, self.tracker)
        with self.tracker.open(encoding="utf-8-sig", newline="") as stream:
            after = list(csv.DictReader(stream))
        self.assertTrue(after[0]["Notes"].startswith("'="))

    def test_dashboard_uses_real_run_history_and_source_provenance(self):
        run = {"status": "success", "started_at": "2026-10-22T10:00:00+00:00", "added": 1,
               "unresolved": 2, "sources_checked": 3}
        record_run(self.path, run)
        (self.path / 'job_metadata.json').write_text(json.dumps({"https://jobs.example.com/1": {
            "category": "AI/ML", "added_at": "2026-10-22T10:00:00+00:00"}}))
        data = load_state(self.tracker, self.path / 'job_metadata.json', self.path / 'scrape_runs.jsonl')
        self.assertEqual(data["metrics"]["total"], 1)
        self.assertEqual(data["jobs"][0]["source"], "AI/ML")
        self.assertEqual(data["runs"][0]["added"], 1)

    def test_scraper_metadata_records_only_new_jobs(self):
        fresh = Job('new-job-id', 'Other Co', 'ML Engineer', 'Remote', 'https://jobright.ai/jobs/info/x', 'AI/ML')
        new_row = {"Company": "Other Co", "Role": "ML Engineer", "Link": "https://apply.example.com/2",
                   "Location": "Remote", "Stage": "Not Applied", "To-do": "Yes", "Notes": ""}
        record_metadata(self.path, [(fresh, new_row['Link'])], self.rows, self.rows + [new_row])
        metadata = json.loads((self.path / 'job_metadata.json').read_text())
        self.assertEqual(metadata[new_row['Link']]['category'], 'AI/ML')
        self.assertNotIn(self.rows[0]['Link'], metadata)


class ConnectorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.config = self.folder / 'destinations.local.json'
        self.tracker = self.folder / 'jobs.csv'
        with self.tracker.open('w', newline='', encoding='utf-8-sig') as stream:
            writer=csv.DictWriter(stream,fieldnames=HEADERS)
            writer.writeheader()
            writer.writerow({"Company":"Example", "Role":"Researcher", "Link":"https://apply.example.com/123",
                             "Location":"CA", "Stage":"Not Applied", "To-do":"Yes", "Notes":""})

    def test_config_prevents_duplicate_destinations(self):
        settings = config_template()
        settings['destinations'].append({'type': 'csv', 'enabled': True})
        with self.assertRaises(DestinationError):
            save_config(settings, self.config)

    def test_never_expose_webhook_url(self):
        config = config_template()
        for dest in config['destinations']:
            if dest['type'] == 'webhook':
                dest.update(enabled=True,url='https://example.com/endpoint?token=secret')
        save_config(config, self.config)
        actual = public_config(self.config)
        self.assertNotIn('secret', json.dumps(actual))
        self.assertTrue(next(x for x in actual['destinations'] if x['type']=='webhook')['configured'])

    def test_environment_secret_supports_scheduled_connectors(self):
        config = config_template()
        # Select by stable connector type, not list index: new integrations
        # (such as Excel) must not break unrelated configuration tests.
        next(x for x in config['destinations'] if x['type'] == 'json')['enabled'] = True
        with patch.dict(os.environ, {'CAREEROPS_DESTINATIONS_JSON':json.dumps(config)}):
            found = load_config(self.config)
        self.assertTrue(next(x for x in found['destinations'] if x['type']=='json')['enabled'])
        self.assertFalse(next(x for x in found['destinations'] if x['type']=='excel')['enabled'])

    def test_reject_private_and_insecure_webhooks(self):
        for url in ['http://example.com/x','https://localhost/api','https://127.0.0.1/xx',
                    'https://10.0.0.1/callback','https://192.168.1.20/a','https://user:pass@example.com']:
            with self.subTest(url=url), self.assertRaises(DestinationError):
                validate_webhook_url(url)

    def test_json_and_pdf_exports_are_real_files(self):
        config = config_template()
        for d in config['destinations']:
            if d['type'] in ('json','pdf'):
                d['enabled'] = True
        save_config(config,self.config)
        result = export_all(self.tracker,self.config, self.folder / 'exports')
        self.assertEqual(len(result['results']),3)
        self.assertTrue(all(r['status']=='success' for r in result['results']))
        self.assertEqual(json.loads((self.folder/'exports/jobs.json').read_text())['jobs'][0]['Role'],'Researcher')
        self.assertTrue((self.folder/'exports/careerops-report.pdf').read_bytes().startswith(b'%PDF-'))


if __name__ == '__main__':
    unittest.main()