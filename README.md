# 2027 New Grad Daily SWE + Data Engineering + AI/ML Scraper

Scrapes three new-grad feeds daily: [Software Engineering](https://www.newgrad-jobs.com/?k=swe), [Data Engineering](https://www.newgrad-jobs.com/?k=de), and [AI/ML](https://www.newgrad-jobs.com/?k=aiml) and appends **only verified non-Jobright application URLs** to the attached CSV tracker.

## What it does

- Loads all three source URLs and their actual embedded Jobright feeds:
  - `?k=swe` → `/minisites-jobs/newgrad/us/swe?embed=true`
  - `?k=de` → `/minisites-jobs/newgrad/us/data_engineer?embed=true`
  - `?k=aiml` → `/minisites-jobs/newgrad/us/ml_ai?embed=true`
- Deduplicates shared jobs across all three feeds using Jobright job IDs before following application links.
- Parses the feed's Next.js `__NEXT_DATA__` JSON and watches additional paginated JSON responses while scrolling, up to a **per-feed** limit (default 50 per source, for up to 150 listings before cross-feed deduplication).
- Visits the Jobright detail page for each listing not already present in the CSV, tries published application-URL fields, or follows **Apply Now** in a browser to the company/ATS application page.
- If a source fails to load, the run aborts without overwriting the tracker. If there is no confirmed external URL (requires login, blocked browser popup, unavailable job, etc.), **does not add it**. It writes the job to `unresolved_jobs.csv` with its category for manual inspection instead.
- Preserves all 93 existing rows, including application stages, notes, and follow-up choices. New rows have Stage=`Not Applied`, To-do=`Yes`, Notes blank.
- Never modifies or submits applications. Never places `jobright.ai` links in the tracker’s `Link` column.

## Run locally

Requires Python 3.12+.

```bash
pip install -r requirements.txt
python -m playwright install chromium
python scraper.py
```

For a quick test:

```bash
python scraper.py --max-jobs-per-source 10 --scroll-steps 2
```

To adjust the daily volume, set `MAX_JOBS_PER_SOURCE` in `.github/workflows/daily-scrape.yml` or pass `--max-jobs-per-source N` locally. The old `--max-jobs` flag remains an alias and also acts per source. You can also pass `--csv path/to/file.csv`. Its headers must exactly match:
`Company,Role,Link,Location,Stage,To-do,Notes`.

## Run daily with GitHub Actions (free-tier eligible, subject to GitHub usage limits)

1. Extract this project folder into a **private GitHub repository** and commit its files **including `.github/workflows/daily-scrape.yml`**. Your CSV remains in the project root.
2. Open the repository's **Actions** tab, select **Daily new grad SWE, DE and AI/ML jobs**, and click **Run workflow** to test the first run.
3. Verify `2027 New Grad Positions Tracker - Sheet1.csv` and `unresolved_jobs.csv` were updated in the repository. The workflow automatically runs **at 13:00 UTC each day** (9 AM Eastern Daylight Time / 8 AM Eastern Standard Time).
4. Keep your manually tracked stages and notes up to date *in the repository's CSV*. If you edit a different local copy, those edits will not sync back automatically.

The workflow needs permission to write repository contents. If pushes fail, set **Settings → Actions → General → Workflow permissions → Read and write permissions**, subject to your organization policy. Scheduled workflows can run late or be disabled for inactive repositories.

## Important limitations

- Each source feed currently provides the initial 50 rows as `__NEXT_DATA__` and additional entries via a dynamic table. The script captures data from that table as it loads. If the site's layout or API changes, the script may need updating. **Not every one of each feed's thousands of older listings will necessarily be retrieved in one run**; the workflow prioritizes recent listings from each category and its per-feed limit.
- A Jobright listing does **not** intrinsically contain a verified employer application URL. The scraper must activate the **Apply Now** action, which may be gated, blocked, or may redirect through another site. For those cases, the job is deliberately left out rather than falsely labeling a Jobright link as the employer application.
- Aggregator links (Jobright, LinkedIn, Indeed, etc.) are not treated as employer applications; direct ATS providers (Workday, Greenhouse, Lever, Ashby, company careers) are allowed.
- Jobs may close after scraping. Always review the final application page before applying.
- Respect the websites' acceptable-use terms, rate limits and restrictions. No CAPTCHA or login bypass is attempted.
- Testing was completed on static fixtures. This sandbox environment cannot launch a live end-to-end scrape over the Internet, so the first GitHub Actions run is the actual integration test.
