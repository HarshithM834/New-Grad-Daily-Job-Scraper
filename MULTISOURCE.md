# CareerOps multi-source collection

CareerOps collects new-grad and entry-level positions from **six independent providers**: newgrad-jobs.com (three SWE/DE/AI/ML feeds), SimplifyJobs, New Grad 2027 by V, SpeedyApply SWE 2027, SpeedyApply AI/ML 2027, and ApplyGuy 2027.

## Quick start

```bash
pip install -r requirements.txt
python -m playwright install chromium
# Preview community feeds; no files are changed and Jobright is skipped.
python careerops.py --dry-run
# Run all six sources and selected output destinations.
python careerops.py
# Limit source counts while debugging:
python careerops.py --max-jobs-per-source 10 --max-per-community 15
# Community-only collector, no Chromium needed:
python careerops.py --skip-jobright
# Particular sources or categories:
python careerops.py --community-feeds simplify,vansh --categories SWE,DE
```

## Source behaviors

| Provider | Feed | Parsing | URL handling |
| --- | --- | --- | --- |
| newgrad-jobs.com | 3 Jobright-backed feeds | Playwright, Next.js data | Click original Apply Now; keep unresolved entries in queue |
| SimplifyJobs | New Grad Positions on GitHub | HTML table | Use first job-specific direct employer link |
| New Grad 2027 by V | README Markdown | Markdown table | Original employer/ATS URL |
| SpeedyApply SWE 2027 | NEW_GRAD_USA.md | Markdown table | Original employer/ATS URL (not internship page) |
| SpeedyApply AI/ML 2027 | NEW_GRAD_USA.md | Markdown table | Original employer/ATS URL (not internship page) |
| ApplyGuy 2027 | data/new-grad-jobs.json | JSON | Use `listingUrl` (not the ApplyGuy redirect) |

Filters reject titles explicitly labeled senior, staff, leadership, or internship; current community feeds provide additional *curated new-grad* context. **A title alone does not establish true experience requirements.** For Jobright, only explicitly junior/graduate titles are accepted by default. `--include-ambiguous` allows users to review unclassified titles.

GitHub-supplied employer links are **structurally screened but not tested for an active application**. Jobright redirects are attempted in a browser and can remain unresolved. Sources can change format, disappear, rate-limit requests, or include stale/duplicate postings. Partial source failures are preserved in run diagnostics and cause the CLI to exit nonzero; successful source data is not discarded.

## Output destinations

Choose outputs through the local dashboard's Output Destinations page or `destinations.local.json` (excluded from Git). CSV, JSON, printable PDF, Google Sheets, and HTTPS webhooks use the existing connector architecture. XLSX export is optionally supported with the `artifact_tool` Python package where available; absence of that package does not affect other outputs. Google Sheets uses a user-provided service account credential and spreadsheet ID. Webhooks require a destination-controlled HTTPS endpoint.

## Scheduling

The GitHub Actions workflow runs `python careerops.py` daily with `CAREEROPS_GITHUB_SOURCES=all`. Change the environment variables or use `workflow_dispatch` to run immediately. The scheduled job may take a while if many Jobright listings need browser resolution.

**Personal data warning:** The public demo repository currently includes a real application tracker in its history. Before distributing the project as a general open-source template, migrate user tracking data to ignored local files (or private storage), remove personally identifiable tracking details from history as appropriate, and ship anonymized sample rows only. Never commit Google credentials, notes, private webhook tokens, or personally identifying records.

Third-party repositories have their own copyright and usage requirements. CareerOps reads those URLs on demand and attributes the sources; no third-party feed content is bundled.