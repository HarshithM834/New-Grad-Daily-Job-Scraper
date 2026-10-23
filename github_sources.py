"""Opt-in, read-only adapters for maintained community new-grad GitHub lists.

These are third-party curated listings, not independent employer verification.
Their licensing and availability remain the responsibility of their publishers.
No source content is bundled with CareerOps; it is fetched on demand.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import time
from dataclasses import dataclass
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from entry_level import classify_role


@dataclass(frozen=True)
class Source:
    id: str
    category: str
    url: str
    format: str
    attribution: str


SOURCES: tuple[Source, ...] = (
    Source("simplify", "mixed", "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/README.md", "simplify_html", "https://github.com/SimplifyJobs/New-Grad-Positions"),
    Source("vansh", "mixed", "https://raw.githubusercontent.com/vanshb03/New-Grad-2027/dev/README.md", "markdown", "https://github.com/vanshb03/New-Grad-2027"),
    Source("speedy-swe", "SWE", "https://raw.githubusercontent.com/speedyapply/2027-SWE-College-Jobs/main/NEW_GRAD_USA.md", "markdown", "https://github.com/speedyapply/2027-SWE-College-Jobs"),
    Source("speedy-aiml", "AI/ML", "https://raw.githubusercontent.com/speedyapply/2027-AI-College-Jobs/main/NEW_GRAD_USA.md", "markdown", "https://github.com/speedyapply/2027-AI-College-Jobs"),
    Source("applyguy", "SWE", "https://raw.githubusercontent.com/ApplyGuy/2027-New-Grad-Jobs/main/data/new-grad-jobs.json", "applyguy_json", "https://github.com/ApplyGuy/2027-New-Grad-Jobs"),
)
SOURCE_IDS = {s.id for s in SOURCES}
AGGREGATOR_HOSTS = {
    "jobright.ai", "newgrad-jobs.com", "simplify.jobs", "applyguy.ai",
    "linkedin.com", "indeed.com", "glassdoor.com", "ziprecruiter.com",
    "speedyapply.com", "github.com", "gitlab.com", "google.com",
    "t.co", "bit.ly", "linktr.ee",
}
TRACKING = {"ref", "source", "trk", "gh_src", "referrer", "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"}


@dataclass(frozen=True)
class ListedJob:
    company: str
    role: str
    location: str
    application_url: str
    source_id: str
    category: str
    source_page: str

    @property
    def job_id(self) -> str:
        normalized = canonical_url(self.application_url)
        return "curated:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:22]


def canonical_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
             if k.lower() not in TRACKING and not k.lower().startswith("utm_")]
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), urlencode(sorted(query)), ""))


def direct_application_url(url: str) -> str | None:
    """Confirm a provider-supplied URL is an external *posting*, not aggregator or homepage.

    Does not make a network request, so closed postings may still be listed.
    """
    if not isinstance(url, str) or not url.strip():
        return None
    try:
        parsed = urlsplit(url.strip())
        host = (parsed.hostname or "").lower()
    except ValueError:
        return None
    if parsed.scheme not in {"https", "http"} or not host or parsed.username or parsed.password:
        return None
    if host == "localhost" or host.endswith((".local", ".internal")) or host.startswith("127."):
        return None
    # Google Careers is one of the exceptions to our aggregator blacklist.
    if host in {"www.google.com", "google.com"} and parsed.path.startswith("/about/careers/applications/jobs/"):
        return url.strip()
    if any(host == h or host.endswith("." + h) for h in AGGREGATOR_HOSTS):
        return None
    from scraper_reliability import employer_application_url
    if not employer_application_url(url, blocked_hosts=AGGREGATOR_HOSTS - {"google.com"}):
        return None
    if parsed.path in {"", "/", "/careers", "/jobs", "/apply"}:
        return None
    return url.strip()


def plain(fragment: str) -> str:
    fragment = re.sub(r"<br\s*/?>", ", ", fragment, flags=re.I)
    fragment = re.sub(r"<[^>]+>", " ", fragment)
    fragment = html.unescape(fragment)
    fragment = re.sub(r"[*_`]+", "", fragment)
    return re.sub(r"\s+", " ", fragment).strip()


def anchor_urls(fragment: str) -> list[str]:
    return [html.unescape(u) for u in re.findall(r"<a\b[^>]*?href\s*=\s*['\"]([^'\"]+)['\"]", fragment, re.I | re.S)]


def category_for_role(role: str, default: str = "SWE") -> str:
    role = role.casefold()
    if re.search(r"\b(data engineer|etl engineer|analytics engineer|data platform)\b", role):
        return "DE"
    if re.search(r"\b(machine learning|deep learning|ai engineer|artificial intelligence|data scientist|data science|ml engineer|applied scientist|research scientist|llm)\b", role):
        return "AI/ML"
    return default


def infer_mixed_category(role: str) -> str | None:
    role_lower = role.casefold()
    if re.search(r"\b(data engineer|etl engineer|analytics engineer|data platform)\b", role_lower):
        return "DE"
    if re.search(r"\b(machine learning|deep learning|ai engineer|artificial intelligence|data scientist|data science|ml engineer|applied scientist|research scientist|llm)\b", role_lower):
        return "AI/ML"
    if re.search(r"\b(software|developer|backend|back.end|front.end|full.stack|sre|site reliability|devops|firmware|embedded|cloud engineer|security engineer|platform engineer|systems engineer|test engineer)\b", role_lower):
        return "SWE"
    return None


def eligible_curated_role(title: str) -> bool:
    """Trust a dedicated graduate list as positive evidence, not senior/intern titles.

    An unmarked software engineer title can be entry level in a graduate list;
    the upstream inclusion is evidence, but independently verify before applying.
    """
    if re.search(r"\b(intern(?:ship)?|co[- ]?op|apprentice|working student)\b", title, re.I):
        return False
    return classify_role(title) != "unlikely"


def _record(company: str, role: str, location: str, url: str, source: Source, category: str | None = None) -> ListedJob | None:
    url = direct_application_url(url)
    company, role, location = plain(company), plain(role), plain(location)
    if not url or not company or not role or company in {"↳", "Company"} or len(role) > 300 or not eligible_curated_role(role):
        return None
    if source.category == "mixed" and category is None:
        assigned = infer_mixed_category(role)
        if assigned is None:
            return None
    else:
        assigned = category_for_role(role, category or source.category)
    return ListedJob(company, role, location, url, source.id, assigned, source.attribution)


def parse_simplify(text: str, source: Source) -> list[ListedJob]:
    items = []
    for section in re.split(r"(?=^##\s)", text, flags=re.M):
        title = section.splitlines()[0].lower() if section.strip() else ""
        if "software engineering new grad" in title:
            category = "SWE"
        elif "data science" in title and ("machine learning" in title or "ai" in title):
            category = "AI/ML"
        else:
            continue
        previous_company = ""
        for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", section, flags=re.I | re.S):
            cells = re.findall(r"<td\b[^>]*>(.*?)</td>", row, flags=re.I | re.S)
            if len(cells) < 4 or "🔒" in row or "application closed" in row.lower():
                continue
            company = plain(cells[0])
            if company in {"↳", ""}:
                company = previous_company
            else:
                company = re.sub(r"^[🔥🛂🇺🇸🎓\s]+", "", company)
                previous_company = company
            link = next((u for u in anchor_urls(cells[3]) if direct_application_url(u)), "")
            job = _record(company, cells[1], cells[2], link, source, category)
            if job:
                items.append(job)
    return items


def parse_markdown(text: str, source: Source) -> list[ListedJob]:
    """Parse the publisher's pipe tables and only the explicitly linked apply column."""
    items = []
    col: dict[str, int] = {}
    previous_company = ""
    for line in text.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 5:
            continue
        headings = [plain(x).lower() for x in cells]
        if "company" in headings and ("role" in headings or "position" in headings):
            col = {name: i for i, name in enumerate(headings)}
            previous_company = ""
            continue
        if not col or set("-: ") >= set("".join(cells)):
            continue
        def cell(*names: str) -> str:
            for name in names:
                if name in col and col[name] < len(cells):
                    return cells[col[name]]
            return ""
        company = plain(cell("company"))
        if company in {"↳", ""}:
            company = previous_company
        else:
            previous_company = company
        role = cell("role", "position")
        location = cell("location")
        link_cell = cell("application/link", "posting", "apply", "application")
        if "🔒" in line or re.search(r"\bclosed\b", plain(link_cell), re.I):
            continue
        link = next((u for u in anchor_urls(link_cell) if direct_application_url(u)), "")
        if not link:
            # Some tables use [Apply](https://...) rather than HTML anchors.
            for u in re.findall(r"\[[^]]+\]\((https?://[^)]+)\)", link_cell):
                if direct_application_url(u):
                    link = u
                    break
        job = _record(company, role, location, link, source)
        if job:
            items.append(job)
    return items


def parse_applyguy(text: str, source: Source) -> list[ListedJob]:
    payload = json.loads(text)
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        raise ValueError("ApplyGuy JSON feed missing jobs list")
    items = []
    for row in payload["jobs"]:
        if not isinstance(row, dict):
            continue
        # listingUrl is the original employer site. url is often an ApplyGuy redirect.
        raw_url = row.get("listingUrl") or row.get("url") or ""
        job = _record(str(row.get("company") or ""), str(row.get("title") or ""),
                      str(row.get("location") or ""), raw_url, source)
        if job:
            items.append(job)
    return items


PARSERS: dict[str, Callable[[str, Source], list[ListedJob]]] = {
    "simplify_html": parse_simplify,
    "markdown": parse_markdown,
    "applyguy_json": parse_applyguy,
}


def select_sources(names: str) -> tuple[Source, ...]:
    if names.strip().lower() in {"all", "*"}:
        return SOURCES
    wanted = [n.strip().lower() for n in names.split(",") if n.strip()]
    invalid = set(wanted) - SOURCE_IDS
    if invalid:
        raise ValueError(f"Unknown GitHub source(s): {', '.join(sorted(invalid))}. Valid: {', '.join(sorted(SOURCE_IDS))}")
    if len(wanted) != len(set(wanted)):
        raise ValueError("Repeated GitHub source identifiers")
    return tuple(s for s in SOURCES if s.id in wanted)


def fetch_source(source: Source, timeout: float = 18, retries: int = 2) -> list[ListedJob]:
    """Bounded GET fetch. No authentication and no HTML page scraping needed."""
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            request = Request(source.url, headers={"User-Agent": "CareerOps-Open-Source/1.0", "Accept": "text/plain, application/json"})
            with urlopen(request, timeout=timeout) as response:
                if response.status != 200:
                    raise RuntimeError(f"HTTP {response.status}")
                content = response.read(9 * 1024 * 1024 + 1)
            if len(content) > 9 * 1024 * 1024:
                raise ValueError("Source feed exceeded 9 MiB limit")
            jobs = PARSERS[source.format](content.decode("utf-8-sig"), source)
            if not jobs:
                raise ValueError(f"Source {source.id} returned no valid applications; format may have changed")
            # Collapse repeated source rows by stable direct application URL.
            return list({canonical_url(j.application_url): j for j in jobs}.values())
        except (HTTPError, URLError, TimeoutError, UnicodeError, ValueError, OSError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(min(2 ** attempt, 3))
    raise RuntimeError(f"Unable to fetch/parse curated source {source.id}: {last_error}")


def import_into_tracker(csv_path, selected: tuple[Source, ...], max_per_source: int = 50,
                        allowed_categories: tuple[str, ...] | None = None, dry_run: bool = False,
                        new_grad_only: bool = True) -> dict:
    """Collect curator-provided direct links, preserving every existing tracker row.

    Partial failure is explicitly reported. This never submits applications.
    """
    from collections import Counter
    from datetime import datetime, timezone
    from pathlib import Path
    from scraper import Job, merge_rows, read_tracker, record_metadata, record_run, write_csv_atomic

    path = Path(csv_path)
    existing = read_tracker(path)
    counts: dict[str, int] = {}
    errors: dict[str, str] = {}
    seen: set[str] = set()
    candidates: list[tuple[Job, str]] = []
    provenance: dict[str, Source] = {}
    started = datetime.now(timezone.utc)
    for source in selected:
        try:
            fetched = fetch_source(source)
            eligible = [j for j in fetched if (allowed_categories is None or j.category in allowed_categories)
                        and (not new_grad_only or eligible_curated_role(j.role))]
            batch = eligible[:max_per_source]
            counts[source.id] = len(batch)
            for item in batch:
                if item.job_id in seen:
                    continue
                seen.add(item.job_id)
                candidates.append((Job(item.job_id, item.company, item.role, item.location,
                                       item.application_url, item.category), item.application_url))
                provenance[canonical_url(item.application_url)] = source
        except Exception as exc:
            errors[source.id] = f"{type(exc).__name__}: {str(exc)[:170]}"
    if not counts:
        raise RuntimeError("All selected GitHub feeds failed; tracker was not changed: " + str(errors))

    merged, added = merge_rows(existing, candidates)
    if added and not dry_run:
        write_csv_atomic(path, merged)
        record_metadata(path.parent, candidates, existing, merged)
        # Provenance stays in the metadata sidecar, preserving the seven-column CSV.
        metadata_file = path.parent / "job_metadata.json"
        try:
            current_meta = json.loads(metadata_file.read_text(encoding="utf-8"))
            if not isinstance(current_meta, dict):
                current_meta = {}
            existing_urls = {canonical_url(row.get("Link", "")) for row in existing}
            new_urls = {canonical_url(row.get("Link", "")) for row in merged} - existing_urls
            for job, link in candidates:
                if canonical_url(link) not in new_urls:
                    continue
                # Find source identity from source-page URL rather than guessing.
                owner = provenance.get(canonical_url(link))
                entry = current_meta.setdefault(link, {})
                if owner:
                    entry.update(source_id=owner.id, source_page=owner.attribution,
                                 eligibility="curated-new-grad")
                else:
                    entry.update(source_id="community", eligibility="curated-new-grad")
            from tempfile import NamedTemporaryFile
            with NamedTemporaryFile("w", dir=path.parent, encoding="utf-8", delete=False,
                                    prefix=".careerops-meta-", suffix=".json") as tmp:
                json.dump(current_meta, tmp, indent=2, ensure_ascii=False)
                temp_meta = tmp.name
            from os import replace as atomic_replace
            atomic_replace(temp_meta, metadata_file)
        except (OSError, ValueError):
            pass  # CSV success must not be rolled back if the optional sidecar fails
    stats = {
        "started_at": started.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "status": "partial" if errors else "success",
        "origin": "curated-github",
        "sources_checked": len(counts),
        "collected": sum(counts.values()),
        "unique_candidates": len(candidates),
        "added": 0 if dry_run else added,
        "would_add": added,
        "dry_run": dry_run,
        "tracker_total": len(existing) if dry_run else len(merged),
        "categories": dict(Counter(job.category for job, _ in candidates)),
        "entry_level_filter": new_grad_only,
        "source_counts": counts,
        "source_errors": errors,
    }
    if not dry_run:
        record_run(path.parent, stats)
    return stats


def main() -> None:
    """Opt-in companion CLI that avoids changing the existing Jobright scraper."""
    import argparse
    import os
    from pathlib import Path
    parser = argparse.ArgumentParser(description="Import direct new-grad application links from public GitHub job lists")
    parser.add_argument("--csv", type=Path, default=Path(os.getenv("CAREEROPS_CSV_PATH", "2027 New Grad Positions Tracker - Sheet1.csv")))
    parser.add_argument("--feeds", default=os.getenv("CAREEROPS_GITHUB_SOURCES", "all"),
                        help="Comma-separated source ids, or all; default all")
    parser.add_argument("--max-per-source", type=int, default=50)
    parser.add_argument("--categories", default="all", help="SWE,DE,AI/ML or all")
    parser.add_argument("--dry-run", action="store_true", help="Preview imported job counts without writing files")
    args = parser.parse_args()
    if args.max_per_source < 1:
        parser.error("--max-per-source must be positive")
    try:
        from entry_level import select_categories
        selected = select_categories(args.categories)
        chosen = select_sources(args.feeds)
        if not chosen:
            parser.error("Choose at least one source")
        stats = import_into_tracker(args.csv, chosen, args.max_per_source, selected, args.dry_run, new_grad_only=True)
    except (ValueError, RuntimeError, OSError) as exc:
        parser.exit(1, f"Source import failed: {exc}\n")
    print(json.dumps(stats, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()