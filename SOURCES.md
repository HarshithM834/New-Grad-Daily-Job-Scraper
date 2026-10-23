# Community job-list sources

CareerOps can **optionally** import new-grad positions from maintained public GitHub lists. This is a separate, read-only import command; the existing Jobright Playwright scraper remains unchanged. No login or paid API is needed.

## Available source IDs

| ID | Maintainer/list | Read target | Coverage |
| --- | --- | --- | --- |
| `simplify` | [SimplifyJobs/New-Grad-Positions](https://github.com/SimplifyJobs/New-Grad-Positions) | `dev/README.md` | SWE; AI/ML; DE subset (some 2026 roles) |
| `vansh` | [vanshb03/New-Grad-2027](https://github.com/vanshb03/New-Grad-2027) | `dev/README.md` | SWE/DE/AI-ML tech positions |
| `speedy-swe` | [speedyapply/2027-SWE-College-Jobs](https://github.com/speedyapply/2027-SWE-College-Jobs) | `main/NEW_GRAD_USA.md` | **New-grad US roles only**, no internship rows |
| `speedy-aiml` | [speedyapply/2027-AI-College-Jobs](https://github.com/speedyapply/2027-AI-College-Jobs) | `main/NEW_GRAD_USA.md` | New-grad US ML/AI/data science roles |
| `applyguy` | [ApplyGuy/2027-New-Grad-Jobs](https://github.com/ApplyGuy/2027-New-Grad-Jobs) | `main/data/new-grad-jobs.json` | Entry-level/new-grad software roles |

## Usage

Install dependencies from the root project, then:

```bash
# Import up to 50 direct-application listings from each source.
python github_sources.py --feeds all --max-per-source 50

# Only SWE and AI/ML, from two selected sources.
python github_sources.py --feeds speedy-swe,speedy-aiml --categories SWE,AI/ML --max-per-source 100

# Your own CSV tracker with the standard seven columns.
python github_sources.py --feeds simplify,vansh --csv /path/to/my-jobs.csv

# Run offline parser tests.
python -m unittest discover -s tests -v
```

The importer **preserves existing application stages, notes, and follow-ups**. Duplicates use the existing scraper's URL and normalized identity checks. It only takes links supplied in each table's application column or ApplyGuy's `listingUrl`; it does not guess employer URLs from company names. It skips closed or non-direct listings and writes source-level success/failure diagnostics to `scrape_runs.jsonl`.

### Enable automatic daily import (optional)

In your GitHub repository, open **Settings → Secrets and variables → Actions → Variables** and add a repository variable named **`CAREEROPS_GITHUB_FEEDS`** with value `all` (or a comma-separated subset). The existing daily scraping workflow will then also import community jobs after the normal scraper. Leave the variable unset to keep the previous behavior.

> **Privacy:** The repository currently includes a personal tracker committed in earlier versions. Before publishing or demoing, replace it with a sanitized example and consider cleaning past Git history. Do not put tokens or personal notes in a public repository.

## Provenance and limits

- These are **curated third-party sources**, not original employer APIs. A provider-supplied direct URL is **not independently verified as live** by this importer. Follow the employer site before applying.
- Source lists are mutable; their Markdown and JSON layouts can change without warning. If parsing yields no jobs, import fails that source with an explicit diagnostic instead of claiming success.
- Lists may overlap. The same employer posting may appear in multiple lists and should be counted once.
- `simplify` includes 2026 graduation-cycle opportunities as well as some 2027 roles. Neither the year nor degree requirements are perfectly filtered. Use the dashboard to review results.
- The importer fetches original Markdown/JSON at execution time and does not vendor the third-party datasets. Respect each source's attribution, licenses, and request policies; keep requests modest. Avoid presenting curated third-party datasets as CareerOps's own listings.
- This adds job-list **sources**, not invasive website scraping. Future direct ATS integrations should prefer documented public read-only endpoints (e.g., Greenhouse Job Board API) over scraping rendered pages.