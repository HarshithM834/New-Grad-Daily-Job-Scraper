"""Small, dependency-free reliability helpers for the CareerOps scraper.

Do not mistake any arbitrary external link for a verified application URL.
Keep unresolved candidates between runs so transient failures remain actionable.
"""

from __future__ import annotations

import csv
import ipaddress
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit, urlunsplit

DEFAULT_BLOCKED_HOSTS = frozenset({
    "jobright.ai", "newgrad-jobs.com", "linkedin.com", "indeed.com",
    "glassdoor.com", "ziprecruiter.com", "monster.com", "talent.com",
    "simplyhired.com", "facebook.com", "google.com", "youtube.com",
    "t.co", "bit.ly", "tinyurl.com", "lnkd.in", "linktr.ee",
    "simplify.jobs", "applyguy.ai", "speedyapply.com",
})

# A landing page, search page or authentication gate is not a job application.
GENERIC_PATHS = frozenset({
    "", "/", "/careers", "/career", "/jobs", "/job", "/openings",
    "/opportunities", "/search", "/job-search", "/jobsearch",
    "/apply", "/login", "/signin", "/sign-in", "/register",
    "/en-us", "/en-us/jobs", "/en-us/careers", "/en-us/search",
})
JOB_QUERY_KEYS = frozenset({
    "jobid", "job_id", "job", "gh_jid", "gh_src", "reqid", "req_id",
    "requisition", "requisitionid", "requisition_id", "jobpostingid",
    "job_posting_id", "jid", "opening", "position", "id", "rid",
})
UNRESOLVED_FIELDS = [
    "Category", "Company", "Role", "Location", "Jobright Source (review only)",
    "First Seen", "Last Seen", "Attempts",
]


def employer_application_url(value: str, blocked_hosts=DEFAULT_BLOCKED_HOSTS) -> str | None:
    """Return an *apparent job-specific* external HTTP(S) URL, else None.

    Structural validation is not proof that a job is live. The browser must
    still follow the real apply action; this rejects obvious false positives.
    """
    if not isinstance(value, str) or len(value) > 4096:
        return None
    raw = value.strip()
    try:
        parsed = urlsplit(raw)
        host = (parsed.hostname or "").rstrip(".").lower()
        port = parsed.port  # Reject malformed ports instead of crashing.
    except ValueError:
        return None
    if (parsed.scheme.lower() not in ("https", "http") or not host or
            parsed.username is not None or parsed.password is not None or
            port not in (None, 80, 443)):
        return None
    if host in ("localhost", "localhost.localdomain") or host.endswith((".local", ".internal", ".localhost")):
        return None
    try:
        ip = ipaddress.ip_address(host)
        if not ip.is_global:
            return None
    except ValueError:
        pass
    # Google Careers has real job-specific listings on google.com.
    google_careers = (host in {"google.com", "www.google.com"} and
                      parsed.path.startswith("/about/careers/applications/jobs/results/"))
    if not google_careers and any(host == blocked or host.endswith("." + blocked) for blocked in blocked_hosts):
        return None
    path = re.sub(r"/+", "/", parsed.path).rstrip("/").lower()
    params = {k.lower() for k in parse_qs(parsed.query, keep_blank_values=True)}
    if path in GENERIC_PATHS and not (params & JOB_QUERY_KEYS):
        return None
    if re.search(r"/(?:sign[-_]?in|login|register|auth)(?:/|$)", path):
        return None
    if re.search(r"/(?:redirect|outbound|tracking|click)(?:/|$)", path):
        return None
    # Strip fragments; they frequently contain session/tracking state.
    return urlunsplit((parsed.scheme.lower(), parsed.netloc, parsed.path, parsed.query, ""))


def _identity(source_url: str, company: str = "", role: str = "") -> str:
    match = re.search(r"/jobs/info/([a-z0-9_-]+)", source_url, re.IGNORECASE)
    if match:
        return "jobright:" + match.group(1).lower()
    canonical = urlsplit(source_url)
    if canonical.hostname and canonical.path:
        return (canonical.hostname.lower() + canonical.path.lower()).rstrip("/")
    return "text:" + (company + "|" + role).strip().casefold()


def update_unresolved_queue(path: Path, unresolved, resolved=(), *, now: str | None = None) -> int:
    """Merge current failures into prior review queue and remove resolved IDs.

    ``unresolved`` / ``resolved`` are Job objects with source_url, etc. This
    accepts the original five-column CSV and upgrades it without data loss.
    Writes atomically and does not retain application statuses or notes.
    """
    path = Path(path)
    now = now or datetime.now(timezone.utc).isoformat()
    saved = {}
    if path.exists():
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                source = row.get("Jobright Source (review only)", "")
                if not source:
                    continue
                key = _identity(source, row.get("Company", ""), row.get("Role", ""))
                saved[key] = {keyname: row.get(keyname, "") for keyname in UNRESOLVED_FIELDS}
                saved[key]["First Seen"] = saved[key]["First Seen"] or now
                saved[key]["Last Seen"] = saved[key]["Last Seen"] or now
                saved[key]["Attempts"] = saved[key]["Attempts"] or "1"
    for job in resolved:
        saved.pop(_identity(job.source_url, job.company, job.role), None)
    for job in unresolved:
        key = _identity(job.source_url, job.company, job.role)
        old = saved.get(key)
        tries = int((old or {}).get("Attempts", "0") or 0)
        saved[key] = {
            "Category": job.category,
            "Company": job.company,
            "Role": job.role,
            "Location": job.location,
            "Jobright Source (review only)": job.source_url,
            "First Seen": (old or {}).get("First Seen") or now,
            "Last Seen": now,
            "Attempts": str(tries + 1),
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8-sig", newline="", dir=path.parent,
                                         prefix=".unresolved-", suffix=".csv", delete=False) as fh:
            temp = Path(fh.name)
            writer = csv.DictWriter(fh, fieldnames=UNRESOLVED_FIELDS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(saved.values())
        os.replace(temp, path)
    finally:
        if temp and temp.exists():
            temp.unlink()
    return len(saved)