"""Local-first career intelligence dashboard.

Run `python dashboard_server.py`. Serves only on loopback, reads the existing
seven-column CSV without migrating it, and saves explicit user edits atomically.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import os
import re
import threading
from collections import Counter
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import output_connectors as exports

ROOT = Path(__file__).resolve().parent
CSV_FILE = Path(os.environ.get("CAREEROPS_CSV_PATH", str(ROOT / "2027 New Grad Positions Tracker - Sheet1.csv"))).expanduser().resolve()
RUNS_FILE = ROOT / "scrape_runs.jsonl"
METADATA_FILE = ROOT / "job_metadata.json"
ASSETS = ROOT / "dashboard"
WEB_DIST = ROOT / "web" / "dist"
HEADERS = ["Company", "Role", "Link", "Location", "Stage", "To-do", "Notes"]
STAGES = ["Not Applied", "Applied", "Coding Assessment", "Interview", "Offer", "Declined/Rejected", ""]
FEEDS = [
    {"id": "SWE", "name": "Software Engineering", "url": "https://www.newgrad-jobs.com/?k=swe"},
    {"id": "DE", "name": "Data Engineering", "url": "https://www.newgrad-jobs.com/?k=de"},
    {"id": "AI/ML", "name": "AI / Machine Learning", "url": "https://www.newgrad-jobs.com/?k=aiml"},
    {"id": "simplify", "name": "Simplify New Grad", "url": "https://github.com/SimplifyJobs/New-Grad-Positions"},
    {"id": "vansh", "name": "New Grad 2027 by V", "url": "https://github.com/vanshb03/New-Grad-2027"},
    {"id": "speedy-swe", "name": "SpeedyApply SWE", "url": "https://github.com/speedyapply/2027-SWE-College-Jobs"},
    {"id": "speedy-aiml", "name": "SpeedyApply AI/ML", "url": "https://github.com/speedyapply/2027-AI-College-Jobs"},
    {"id": "applyguy", "name": "ApplyGuy New Grad", "url": "https://github.com/ApplyGuy/2027-New-Grad-Jobs"},
]
AGGREGATORS = {"jobright.ai", "indeed.com", "linkedin.com", "glassdoor.com", "ziprecruiter.com", "monster.com", "newgrad-jobs.com"}
WRITE_LOCK = threading.Lock()
LOGGER = logging.getLogger("job_dashboard")


def cell_safe(value: str) -> str:
    """Defend spreadsheet exports from formula injection."""
    val = value.strip()
    return "'" + val if val.startswith(("=", "+", "-", "@", "\t", "\r")) else val


def row_id(row: dict[str, str]) -> str:
    parts = [row.get(k, "").strip().casefold() for k in ("Company", "Role", "Link", "Location")]
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:20]


def load_csv(path: Path = CSV_FILE) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != HEADERS:
            raise ValueError("Tracker must retain its original seven columns")
        return list(reader)


def save_csv(rows: list[dict[str, str]], path: Path = CSV_FILE) -> None:
    from tempfile import NamedTemporaryFile
    with NamedTemporaryFile(mode="w", encoding="utf-8-sig", newline="", dir=path.parent,
                            prefix=".dashboard-", suffix=".csv", delete=False) as handle:
        tmp = Path(handle.name)
        writer = csv.DictWriter(handle, fieldnames=HEADERS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def safe_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        LOGGER.warning("Unable to parse %s", path.name)
        return default


def load_runs(path: Path = RUNS_FILE) -> list[dict]:
    if not path.exists():
        return []
    output = []
    for line in path.read_text(encoding="utf-8").splitlines()[-100:]:
        try:
            obj = json.loads(line)
            if isinstance(obj, dict) and obj.get("started_at"):
                output.append(obj)
        except (TypeError, ValueError):
            continue
    return output


def is_aggregator(link: str) -> bool:
    host = (urlsplit(link.strip()).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in AGGREGATORS)


def load_state(tracker: Path = CSV_FILE, metadata_path: Path = METADATA_FILE,
               runs_path: Path = RUNS_FILE) -> dict:
    rows = load_csv(tracker)
    meta = safe_json(metadata_path, {})
    if not isinstance(meta, dict):
        meta = {}
    jobs = []
    used_ids = Counter()
    for row in rows:
        identity = row_id(row)
        used_ids[identity] += 1
        # Only append a suffix if the tracker has byte-identical job identities.
        identity = f"{identity}-{used_ids[identity]}" if used_ids[identity] > 1 else identity
        m = meta.get(row.get("Link", ""), {})
        if not isinstance(m, dict):
            m = {}
        jobs.append({
            "id": identity,
            "company": row["Company"], "role": row["Role"],
            "location": row["Location"], "link": row["Link"],
            "stage": row["Stage"], "todo": row["To-do"].strip().lower() == "yes",
            "notes": row["Notes"],
            "source": m.get("category") if m.get("category") in {"SWE", "DE", "AI/ML"} else "Unknown",
            "added_at": m.get("added_at") or None,
            "source_provider": m.get("source_id") or "newgrad-jobs",
            "aggregator": is_aggregator(row["Link"]),
        })
    stages = Counter(j["stage"] or "Uncategorized" for j in jobs)
    sources = Counter(j["source"] for j in jobs)
    missing_links = sum(not j["link"].strip() for j in jobs)
    aggregators = sum(j["aggregator"] for j in jobs)
    seen_key = set()
    duplicates = 0
    for j in jobs:
        key = (j["company"].casefold().strip(), j["role"].casefold().strip(), j["location"].casefold().strip())
        if key in seen_key:
            duplicates += 1
        seen_key.add(key)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(), "jobs": jobs,
        "runs": load_runs(runs_path), "feeds": FEEDS,
        "metrics": {
            "total": len(jobs), "in_progress": sum(stages[k] for k in ("Applied", "Coding Assessment", "Interview")),
            "todo": sum(j["todo"] for j in jobs), "assessments": stages["Coding Assessment"],
            "stages": dict(stages), "sources": dict(sources),
            "quality": {"aggregator_links": aggregators, "missing_links": missing_links,
                        "uncategorized": stages["Uncategorized"], "duplicate_rows": duplicates,
                        "unknown_source": sources["Unknown"]},
        },
    }


def update_job(job_id: str, payload: dict, tracker: Path = CSV_FILE) -> dict:
    if not isinstance(payload, dict) or set(payload) != {"stage", "todo", "notes"}:
        raise ValueError("Expected stage, todo and notes fields")
    if payload["stage"] not in STAGES:
        raise ValueError("Unknown application stage")
    if not isinstance(payload["todo"], bool):
        raise ValueError("To-do must be a boolean")
    if not isinstance(payload["notes"], str) or len(payload["notes"]) > 3000:
        raise ValueError("Notes must be text, maximum 3000 characters")
    with WRITE_LOCK:
        rows = load_csv(tracker)
        used_ids = Counter()
        match = None
        for row in rows:
            identity = row_id(row)
            used_ids[identity] += 1
            identity = f"{identity}-{used_ids[identity]}" if used_ids[identity] > 1 else identity
            if identity == job_id:
                match = row
                break
        if match is None:
            raise KeyError("Job no longer exists; refresh the dashboard")
        match["Stage"] = payload["stage"]
        match["To-do"] = "Yes" if payload["todo"] else "No"
        match["Notes"] = cell_safe(payload["notes"])
        save_csv(rows, tracker)
    return {"id": job_id, "stage": match["Stage"], "todo": payload["todo"], "notes": match["Notes"]}


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "CareerOps/1.0"

    def log_message(self, format: str, *args) -> None:
        LOGGER.info("%s - %s", self.address_string(), format % args)

    def send_headers(self, status: int, content_type: str, payload: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; connect-src 'self'; img-src 'self' data:; script-src 'self'; style-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(payload)

    def reply(self, status: int, obj: dict) -> None:
        self.send_headers(status, "application/json; charset=utf-8", json.dumps(obj, ensure_ascii=False).encode())

    def do_GET(self) -> None:
        route = self.path.split("?", 1)[0]
        if route == "/api/state":
            try:
                self.reply(200, load_state())
            except Exception as exc:
                LOGGER.exception("Failed to read tracker")
                self.reply(500, {"error": "Unable to read tracker", "detail": str(exc)})
            return
        if route == "/api/destinations":
            try:
                self.reply(200, exports.public_config())
            except exports.DestinationError as exc:
                self.reply(400, {"error": str(exc)})
            return
        if route == "/download/tracker.csv":
            self.send_headers(200, "text/csv; charset=utf-8", CSV_FILE.read_bytes())
            return
        if route == "/download/jobs.json":
            payload = {"exported_at": datetime.now(timezone.utc).isoformat(),
                       "jobs": exports.read_jobs(CSV_FILE)}
            self.send_headers(200, "application/json; charset=utf-8", json.dumps(payload).encode())
            return
        if route == "/download/jobs.xlsx":
            try:
                from excel_export import make_xlsx
                path = ROOT / "exports" / "careerops-jobs.xlsx"
                make_xlsx(exports.read_jobs(CSV_FILE), path)
                self.send_headers(200, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", path.read_bytes())
            except Exception:
                LOGGER.exception("Excel export failed")
                self.reply(500, {"error": "Excel export unavailable; install optional artifact_tool"})
            return
        if route == "/download/report.pdf":
            try:
                path = ROOT / "exports" / "careerops-report.pdf"
                exports.make_pdf(exports.read_jobs(CSV_FILE), path)
                self.send_headers(200, "application/pdf", path.read_bytes())
            except Exception:
                LOGGER.exception("PDF export failed")
                self.reply(500, {"error": "PDF report could not be produced"})
            return
        # Prefer the built React dashboard; retain the original local UI if absent.
        if WEB_DIST.is_dir() and (route == "/" or route.startswith("/assets/")):
            candidate = (WEB_DIST / ("index.html" if route == "/" else route.lstrip("/"))).resolve()
            if candidate.is_relative_to(WEB_DIST.resolve()) and candidate.is_file():
                from mimetypes import guess_type
                mime = guess_type(candidate.name)[0] or "application/octet-stream"
                if mime == "text/javascript":
                    mime = "application/javascript"
                self.send_headers(200, mime, candidate.read_bytes())
                return
            self.reply(404, {"error": "Asset not found"})
            return
        static = {"/": ("index.html", "text/html; charset=utf-8"),
                  "/dashboard.css": ("dashboard.css", "text/css; charset=utf-8"),
                  "/dashboard.js": ("dashboard.js", "application/javascript; charset=utf-8"),
                  "/favicon.svg": ("favicon.svg", "image/svg+xml")}
        if route not in static:
            self.reply(404, {"error": "Not found"})
            return
        name, mime = static[route]
        self.send_headers(200, mime, (ASSETS / name).read_bytes())

    def do_POST(self) -> None:
        origin = self.headers.get("Origin", "")
        allowed = f"http://127.0.0.1:{self.server.server_port}"
        host = self.headers.get("Host", "")
        if origin != allowed or host != f"127.0.0.1:{self.server.server_port}":
            self.reply(403, {"error": "Request origin must be the local dashboard"})
            return
        if self.path not in ("/api/job", "/api/destinations", "/api/sync"):
            self.reply(404, {"error": "Not found"})
            return
        if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
            self.reply(415, {"error": "Expected application/json"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 8192:
                self.reply(413, {"error": "Payload too large"})
                return
            data = json.loads(self.rfile.read(length))
            if self.path == "/api/destinations":
                if not isinstance(data, dict):
                    raise ValueError("Invalid destination settings")
                # The UI never asks for credential values. A blank URL preserves
                # an existing configured webhook endpoint rather than exposing it.
                existing = {x["type"]: x for x in exports.load_config()["destinations"]}
                for item in data.get("destinations", []):
                    if item.get("type") == "webhook" and not item.get("url"):
                        item["url"] = existing["webhook"].get("url", "")
                exports.save_config(data)
                self.reply(200, {"saved": True, "settings": exports.public_config()})
                return
            if self.path == "/api/sync":
                result = exports.export_all()
                self.reply(200, result)
                return
            if not isinstance(data, dict) or not isinstance(data.get("id"), str):
                raise ValueError("Missing job identifier")
            identity = data.pop("id")
            saved = update_job(identity, data)
            self.reply(200, {"saved": True, "job": saved})
        except (ValueError, json.JSONDecodeError, exports.DestinationError) as exc:
            self.reply(400, {"error": str(exc)})
        except KeyError as exc:
            self.reply(404, {"error": str(exc)})
        except Exception:
            LOGGER.exception("Failed to save job")
            self.reply(500, {"error": "Failed to save change"})


def main() -> None:
    parser = argparse.ArgumentParser(description="Local-first CareerOps job intelligence dashboard")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # Bind on loopback only: tracker notes are not exposed to other network clients.
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), DashboardHandler)
    print(f"\n  CareerOps dashboard: http://127.0.0.1:{args.port}\n  Control+C to stop.\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()