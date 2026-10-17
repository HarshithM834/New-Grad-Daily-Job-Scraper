"""Daily newgrad-jobs.com SWE, Data Engineering and AI/ML -> 2027 tracker.

The Link column is employer/ATS only. A Jobright-only link is never
substituted for an unresolved application URL.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import os
import re
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from playwright.async_api import Browser, BrowserContext, Frame, Page, Response, async_playwright

LOGGER = logging.getLogger("newgrad_scraper")
@dataclass(frozen=True)
class FeedSource:
    category: str
    page_url: str
    embed_url: str


# The page query names and the underlying Jobright category paths differ.
# Verified against the live pages on 2026-10-17.
SOURCES: tuple[FeedSource, ...] = (
    FeedSource("SWE", "https://www.newgrad-jobs.com/?k=swe",
               "https://jobright.ai/minisites-jobs/newgrad/us/swe?embed=true"),
    FeedSource("DE", "https://www.newgrad-jobs.com/?k=de",
               "https://jobright.ai/minisites-jobs/newgrad/us/data_engineer?embed=true"),
    FeedSource("AI/ML", "https://www.newgrad-jobs.com/?k=aiml",
               "https://jobright.ai/minisites-jobs/newgrad/us/ml_ai?embed=true"),
)
COLUMNS = ["Company", "Role", "Link", "Location", "Stage", "To-do", "Notes"]
BAD_HOSTS = {
    "jobright.ai", "newgrad-jobs.com", "linkedin.com", "indeed.com",
    "glassdoor.com", "ziprecruiter.com", "monster.com", "talent.com",
    "simplyhired.com", "facebook.com", "google.com",
}
APPLY_KEYS = ("applyLink", "originalUrl", "externalUrl", "jobApplyUrl", "applicationUrl", "jobUrl", "applyUrl")


@dataclass(frozen=True)
class Job:
    job_id: str
    company: str
    role: str
    location: str
    source_url: str
    category: str = ""


def safe_cell(value: Any) -> str:
    """Escape spreadsheet formulas in untrusted scraped text."""
    text = str(value or "").strip()
    return "'" + text if text.startswith(("=", "+", "-", "@", "\t", "\r")) else text


def normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def normalized_url(value: str) -> str:
    parsed = urlparse((value or "").strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return ""
    params = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
              if not k.lower().startswith("utm_") and k.lower() not in
              ("gh_src", "source", "ref", "referrer", "trk")]
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(),
                       parsed.path.rstrip("/") or "/", "", urlencode(sorted(params)), ""))


def employer_url(value: str) -> str | None:
    """Never accept aggregator pages, social sites, or Jobright as direct apply."""
    url = (value or "").strip()
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https") or not host:
        return None
    if any(host == block or host.endswith("." + block) for block in BAD_HOSTS):
        return None
    if host in ("localhost", "127.0.0.1"):
        return None
    # Applications frequently have their own third-party ATS domain.
    return url


def extract_jobs(payload: Any) -> list[Job]:
    """Recognize the site's SSR initialJobs and similarly shaped paginated JSON."""
    found: dict[str, Job] = {}

    def visit(value: Any, depth: int = 0) -> None:
        if depth > 12:
            return
        if isinstance(value, list):
            for item in value:
                visit(item, depth + 1)
        elif isinstance(value, dict):
            company = value.get("company")
            role = value.get("title")
            jid = value.get("id") or value.get("jobId")
            # Every listing has this shape in __NEXT_DATA__. Avoid guessing from unrelated JSON.
            if isinstance(company, str) and isinstance(role, str) and isinstance(jid, str):
                src = str(value.get("applyUrl") or f"https://jobright.ai/jobs/info/{jid}")
                found[jid] = Job(jid, safe_cell(company), safe_cell(role),
                                 safe_cell(value.get("location", "")), src)
            else:
                for item in value.values():
                    if isinstance(item, (dict, list)):
                        visit(item, depth + 1)

    visit(payload)
    return list(found.values())


def extract_next_data(html: str) -> list[Job]:
    match = re.search(r'<script\b[^>]*id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
                      html, flags=re.I | re.S)
    if not match:
        return []
    try:
        return extract_jobs(json.loads(match.group(1)))
    except json.JSONDecodeError:
        return []


def find_external_urls(obj: Any, depth: int = 0) -> list[str]:
    """Only select explicit apply/original URL fields, never the company homepage."""
    if depth > 8 or not isinstance(obj, (list, dict)):
        return []
    results: list[str] = []
    if isinstance(obj, list):
        for x in obj:
            results.extend(find_external_urls(x, depth + 1))
    else:
        for key in APPLY_KEYS:
            val = obj.get(key)
            if isinstance(val, str) and (good := employer_url(val)):
                results.append(good)
        for value in obj.values():
            if isinstance(value, (list, dict)):
                results.extend(find_external_urls(value, depth + 1))
    return results


def unique_candidates(rows: list[Job]) -> list[Job]:
    seen: set[str] = set()
    result = []
    for job in rows:
        if job.job_id not in seen:
            seen.add(job.job_id)
            result.append(job)
    return result


async def extract_from_frame(frame: Frame) -> list[Job]:
    try:
        text = await frame.locator("script#__NEXT_DATA__").first.text_content(timeout=7000)
        return extract_jobs(json.loads(text or "{}"))
    except Exception:
        return []


async def collect_jobs(context: BrowserContext, *, source: FeedSource, max_jobs: int, scroll_steps: int) -> list[Job]:
    page = await context.new_page()
    discovered: dict[str, Job] = {}
    pending: set[asyncio.Task] = set()

    async def parse_response(response: Response) -> None:
        try:
            if "jobright.ai" not in response.url or "json" not in (response.headers.get("content-type") or ""):
                return
            body = await response.json()
            for j in extract_jobs(body):
                discovered.setdefault(j.job_id, replace(j, category=source.category))
        except Exception:
            pass

    def handle_response(response: Response) -> None:
        task = asyncio.create_task(parse_response(response))
        pending.add(task)
        task.add_done_callback(pending.discard)

    page.on("response", handle_response)
    try:
        LOGGER.info("Loading %s category from %s", source.category, source.page_url)
        await page.goto(source.page_url, wait_until="domcontentloaded", timeout=45000)
        try:
            await page.wait_for_timeout(2200)
        except Exception:
            pass
        embed_path = urlparse(source.embed_url).path
        iframe = next((f for f in page.frames if embed_path in f.url), None)
        if iframe is None:
            # Direct embed fallback if the parent page changes its iframe handling.
            LOGGER.info("%s iframe not found; opening feed directly", source.category)
            await page.goto(source.embed_url, wait_until="domcontentloaded", timeout=45000)
            iframe = page.main_frame
        for job in await extract_from_frame(iframe):
            discovered.setdefault(job.job_id, job)
        if not discovered:
            try:
                await iframe.locator("script#__NEXT_DATA__").first.wait_for(timeout=12000)
            except Exception:
                pass
            for job in await extract_from_frame(iframe):
                discovered.setdefault(job.job_id, job)
        if not discovered:
            raise RuntimeError("Could not locate structured job listings; site structure may have changed")

        LOGGER.info("Initial job listings: %d", len(discovered))
        unchanged_steps = 0
        for step in range(scroll_steps):
            if len(discovered) >= max_jobs or unchanged_steps >= 7:
                break
            before = len(discovered)
            # Embedded table may scroll internally instead of the document.
            await iframe.evaluate("""() => {
                const nodes = [...document.querySelectorAll('*')].filter(el =>
                  el.scrollHeight > el.clientHeight + 200 &&
                  ['auto','scroll'].includes(getComputedStyle(el).overflowY));
                nodes.sort((a,b) => (b.clientHeight > 100 ? b.scrollHeight-b.clientHeight : 0) -
                                     (a.clientHeight > 100 ? a.scrollHeight-a.clientHeight : 0));
                const target = nodes.find(e => e.clientHeight > 100);
                if (target) target.scrollTop += Math.max(target.clientHeight * 0.9, 500);
                window.scrollBy(0, 800);
                window.scrollTo(0, document.body.scrollHeight);
            }""")
            await page.wait_for_timeout(1250)
            if pending:
                await asyncio.gather(*list(pending), return_exceptions=True)
            for job in await extract_from_frame(iframe):
                discovered.setdefault(job.job_id, job)
            unchanged_steps = unchanged_steps + 1 if len(discovered) == before else 0
            LOGGER.info("Scroll %d: %d unique jobs", step + 1, len(discovered))
        return list(discovered.values())[:max_jobs]
    finally:
        page.remove_listener("response", handle_response)
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        await page.close()


async def collect_all_jobs(context: BrowserContext, *, max_jobs_per_source: int,
                           scroll_steps: int) -> list[Job]:
    """Collect every configured feed; deduplicate one job appearing in multiple feeds.

    A feed failure aborts the run rather than incorrectly claiming all sources
    were checked. Already tracked jobs are not modified by an aborted run.
    """
    gathered: list[Job] = []
    for source in SOURCES:
        batch = await collect_jobs(context, source=source,
                                   max_jobs=max_jobs_per_source,
                                   scroll_steps=scroll_steps)
        LOGGER.info("%s: collected %d rows", source.category, len(batch))
        gathered.extend(batch)
    jobs = unique_candidates(gathered)
    LOGGER.info("Combined feeds: %d candidates, %d unique jobs",
                len(gathered), len(jobs))
    return jobs


async def resolve_direct_link(context: BrowserContext, job: Job, *, wait_ms: int = 2400) -> str | None:
    """Follow Jobright's *actual* Apply Now action to the employer/ATS.

    Never fabricate URLs from company names; if Jobright requires sign-in,
    uses a blocked popup, or offers no external destination, return None.
    """
    direct = employer_url(job.source_url)
    if direct:
        return direct
    page = await context.new_page()
    opened: list[Page] = []
    response_tasks: set[asyncio.Task] = set()
    found_from_api: list[str] = []

    def on_page(p: Page) -> None:
        opened.append(p)

    async def look_in_response(response: Response) -> None:
        try:
            if "jobright.ai" not in response.url:
                return
            if "json" not in (response.headers.get("content-type") or ""):
                return
            if not any(word in response.url.lower() for word in ("apply", "redirect", "job")):
                return
            obj = await response.json()
            found_from_api.extend(find_external_urls(obj))
        except Exception:
            pass

    def on_response(response: Response) -> None:
        task = asyncio.create_task(look_in_response(response))
        response_tasks.add(task)
        task.add_done_callback(response_tasks.discard)

    context.on("page", on_page)
    page.on("response", on_response)
    try:
        detail = f"https://jobright.ai/jobs/info/{job.job_id}"
        await page.goto(detail, wait_until="domcontentloaded", timeout=25000)
        # Some versions embed direct ATS links in an explicit JSON data field.
        for script_id in ("jobright-helper-job-detail-info", "__NEXT_DATA__"):
            try:
                raw = await page.locator(f"script#{script_id}").first.text_content(timeout=1500)
                urls = find_external_urls(json.loads(raw or "{}"))
                if urls:
                    return urls[0]
            except Exception:
                pass
        # An actual employer application link is preferable to a generic company site.
        try:
            links = await page.locator("a[href]").all()
            for anchor in links:
                label = (await anchor.inner_text(timeout=500)).strip().lower()
                if re.search(r"apply (now|on employer|on company|for this)", label):
                    href = await anchor.get_attribute("href")
                    if href and (link := employer_url(href)):
                        return link
        except Exception:
            pass
        button = page.get_by_role("button", name=re.compile(r"APPLY NOW", re.I))
        if await button.count() == 0:
            LOGGER.warning("No Apply Now button for %s — %s", job.company, job.role)
            return None
        await button.first.click(timeout=7000)
        await page.wait_for_timeout(wait_ms)
        if response_tasks:
            await asyncio.gather(*list(response_tasks), return_exceptions=True)
        if found_from_api:
            return found_from_api[0]
        # Most external application links open a new browser tab.
        for target in opened:
            try:
                await target.wait_for_load_state("domcontentloaded", timeout=5500)
            except Exception:
                pass
            if (link := employer_url(target.url)):
                return link
        # Some cases navigate the current tab.
        if (link := employer_url(page.url)):
            return link
        return None
    except Exception as exc:
        LOGGER.warning("Unable to resolve %s / %s: %s", job.company, job.role, exc)
        return None
    finally:
        context.remove_listener("page", on_page)
        page.remove_listener("response", on_response)
        for target in opened:
            if target != page and not target.is_closed():
                try:
                    await target.close()
                except Exception:
                    pass
        if not page.is_closed():
            await page.close()


def merge_rows(existing: list[dict[str, str]], new_jobs: list[tuple[Job, str]]) -> tuple[list[dict[str, str]], int]:
    output = list(existing)
    existing_keys = {(normalized(row.get("Company", "")), normalized(row.get("Role", "")),
                      normalized(row.get("Location", ""))) for row in output}
    existing_links = {normalized_url(row.get("Link", "")) for row in output}
    added = 0
    for job, url in new_jobs:
        direct = employer_url(url)
        if direct is None:
            continue
        key = (normalized(job.company), normalized(job.role), normalized(job.location))
        linkkey = normalized_url(direct)
        if key in existing_keys or (linkkey and linkkey in existing_links):
            continue
        output.append({"Company": safe_cell(job.company), "Role": safe_cell(job.role),
                       "Link": direct, "Location": safe_cell(job.location),
                       "Stage": "Not Applied", "To-do": "Yes", "Notes": ""})
        existing_keys.add(key)
        existing_links.add(linkkey)
        added += 1
    return output, added


def read_tracker(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != COLUMNS:
            raise ValueError(f"Expected exact headers {COLUMNS}, got {reader.fieldnames}")
        return list(reader)


def write_csv_atomic(path: Path, rows: list[dict[str, str]]) -> None:
    import tempfile
    with tempfile.NamedTemporaryFile("w", encoding="utf-8-sig", newline="",
                                     dir=path.parent, prefix=".tracker-", suffix=".csv", delete=False) as f:
        temporary = Path(f.name)
        writer = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


async def run(path: Path, max_jobs: int, scroll_steps: int) -> int:
    existing = read_tracker(path)
    LOGGER.info("Existing tracker: %d rows", len(existing))
    async with async_playwright() as p:
        browser: Browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 1000},
                                            user_agent=("Mozilla/5.0 (X11; Linux x86_64) "
                                                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                                                        "Chrome/130.0.0.0 Safari/537.36"))
        try:
            jobs = await collect_all_jobs(context, max_jobs_per_source=max_jobs,
                                          scroll_steps=scroll_steps)
            already = {(normalized(row.get("Company", "")), normalized(row.get("Role", "")),
                        normalized(row.get("Location", ""))) for row in existing}
            pending = [job for job in jobs if (normalized(job.company), normalized(job.role),
                                               normalized(job.location)) not in already]
            LOGGER.info("Scraped %d; %d not already matched in tracker", len(jobs), len(pending))
            confirmed: list[tuple[Job, str]] = []
            unresolved: list[Job] = []
            for i, job in enumerate(pending, 1):
                url = await resolve_direct_link(context, job)
                if url:
                    confirmed.append((job, url))
                    LOGGER.info("[%d/%d] Found employer URL: %s (%s)",
                                i, len(pending), job.company, url)
                else:
                    unresolved.append(job)
                    LOGGER.info("[%d/%d] Skipped unresolved: %s / %s", i, len(pending),
                                job.company, job.role)
                # Low request rate to avoid overloading source sites.
                await asyncio.sleep(0.7)
            merged, added = merge_rows(existing, confirmed)
            if added:
                write_csv_atomic(path, merged)
            # Secondary log contains Jobright source links solely for manual review;
            # the actual tracker never receives a Jobright URL.
            with (path.parent / "unresolved_jobs.csv").open("w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerow(["Category", "Company", "Role", "Location", "Jobright Source (review only)"])
                for job in unresolved:
                    w.writerow([job.category, job.company, job.role, job.location, job.source_url])
            LOGGER.info("Complete: %d new rows, %d unresolved (tracker total %d)",
                        added, len(unresolved), len(merged))
            return added
        finally:
            await context.close()
            await browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect SWE, DE and AI/ML new grad jobs with real employer links")
    parser.add_argument("--csv", type=Path, default=Path(__file__).parent / "2027 New Grad Positions Tracker - Sheet1.csv")
    parser.add_argument("--max-jobs-per-source", "--max-jobs", dest="max_jobs_per_source",
                        type=int, default=int(os.getenv("MAX_JOBS_PER_SOURCE", os.getenv("MAX_JOBS", "50"))),
                        help="Maximum listings to retrieve from EACH of the three feeds (default: 50)")
    parser.add_argument("--scroll-steps", type=int, default=int(os.getenv("SCROLL_STEPS", "24")))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.max_jobs_per_source < 1 or args.scroll_steps < 0:
        parser.error("--max-jobs-per-source must be positive and --scroll-steps nonnegative")
    if not args.csv.exists():
        parser.error(f"Tracker CSV does not exist: {args.csv}")
    try:
        asyncio.run(run(args.csv, args.max_jobs_per_source, args.scroll_steps))
    except Exception:
        LOGGER.exception("Scraper failed without overwriting the existing tracker")
        sys.exit(1)


if __name__ == "__main__":
    main()
