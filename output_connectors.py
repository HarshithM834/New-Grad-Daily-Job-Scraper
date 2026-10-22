"""Modular output connectors for the CareerOps job tracker.

Tracker CSV remains the source of truth. All destinations are opt-in; a connector
failure does not corrupt the tracker. Credentials are never saved in config or
committed to Git. Google Sheets and webhooks are outbound-only integrations.
"""
from __future__ import annotations

import csv
import io
import ipaddress
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
DEFAULT_CSV = Path(os.environ.get("CAREEROPS_CSV_PATH", str(ROOT / "2027 New Grad Positions Tracker - Sheet1.csv"))).expanduser().resolve()
CONFIG_FILE = ROOT / "destinations.local.json"
COLUMNS = ["Company", "Role", "Link", "Location", "Stage", "To-do", "Notes"]
SUPPORTED = {"csv", "json", "pdf", "google_sheets", "webhook"}


class DestinationError(RuntimeError):
    """Safe, user-actionable connector error."""


def config_template():
    return {"destinations": [
        {"type": "csv", "enabled": True},
        {"type": "json", "enabled": False},
        {"type": "pdf", "enabled": False},
        {"type": "google_sheets", "enabled": False, "spreadsheet_id": "", "worksheet": "Jobs"},
        {"type": "webhook", "enabled": False, "url": ""},
    ]}


def validate_destination(record: dict) -> dict:
    if not isinstance(record, dict) or record.get("type") not in SUPPORTED:
        raise DestinationError("Unsupported destination type")
    kind = record["type"]
    enabled = record.get("enabled", False)
    if not isinstance(enabled, bool):
        raise DestinationError("Destination enabled must be true or false")
    result = {"type": kind, "enabled": enabled}
    if kind == "google_sheets":
        ident = str(record.get("spreadsheet_id", "")).strip()
        tab = str(record.get("worksheet", "Jobs")).strip()
        if len(ident) > 200 or len(tab) > 90 or not tab:
            raise DestinationError("Invalid Google Sheets identifier or tab name")
        if enabled and not ident:
            raise DestinationError("Enter a Google Sheets spreadsheet ID to enable sync")
        result.update(spreadsheet_id=ident, worksheet=tab)
    if kind == "webhook":
        url = str(record.get("url", "")).strip()
        if len(url) > 2000:
            raise DestinationError("Webhook URL is too long")
        if enabled:
            validate_webhook_url(url)
        result["url"] = url
    return result


def validate_webhook_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise DestinationError("Webhook must be an HTTPS URL without embedded credentials")
    host = parsed.hostname.lower()
    if host == "localhost" or host.endswith((".local", ".internal")):
        raise DestinationError("Webhooks cannot target private hosts")
    try:
        ip = ipaddress.ip_address(host)
        if not ip.is_global:
            raise DestinationError("Webhooks must use a publicly routable address")
    except ValueError:
        pass


def load_config(path: Path = CONFIG_FILE) -> dict:
    if not path.exists() and not os.getenv("CAREEROPS_DESTINATIONS_JSON"):
        return config_template()
    try:
        # CI can load a destination config from an Actions secret; no secret file
        # needs to be checked into a repository. Local preferences win when present.
        data = json.loads(path.read_text(encoding="utf-8") if path.exists()
                          else os.environ["CAREEROPS_DESTINATIONS_JSON"])
    except (OSError, ValueError) as exc:
        raise DestinationError("Cannot read destinations.local.json") from exc
    if not isinstance(data, dict) or not isinstance(data.get("destinations"), list):
        raise DestinationError("Destination configuration must contain an array")
    entries = [validate_destination(x) for x in data["destinations"]]
    types = [x["type"] for x in entries]
    if len(types) != len(set(types)):
        raise DestinationError("Only one configuration per destination type is allowed")
    known = {x["type"]: x for x in entries}
    return {"destinations": [known.get(x["type"], x) for x in config_template()["destinations"]]}


def save_config(data: dict, path: Path = CONFIG_FILE) -> dict:
    if not isinstance(data, dict) or not isinstance(data.get("destinations"), list):
        raise DestinationError("Expected destinations array")
    entries = [validate_destination(d) for d in data["destinations"]]
    types = [d["type"] for d in entries]
    if len(types) != len(set(types)) or set(types) != SUPPORTED:
        raise DestinationError("Supply exactly one configuration for each supported destination")
    canonical = {"destinations": entries}
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                     prefix=".destinations-", suffix=".json", delete=False) as f:
        tmp = Path(f.name)
        json.dump(canonical, f, indent=2)
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    return canonical


def public_config(path: Path = CONFIG_FILE) -> dict:
    """Never expose webhook URL in a GET response: it may be a secret endpoint."""
    config = load_config(path)
    sanitized = []
    for entry in config["destinations"]:
        obj = dict(entry)
        if obj["type"] == "webhook":
            obj["configured"] = bool(obj.pop("url", ""))
        sanitized.append(obj)
    return {"destinations": sanitized,
            "credentials": {"google_sheets": bool(os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))}}


def read_jobs(path: Path = DEFAULT_CSV) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != COLUMNS:
            raise DestinationError("Tracker CSV columns don't match the expected schema")
        return list(reader)


def export_json(jobs: list[dict[str, str]], path: Path) -> dict:
    path.write_text(json.dumps({"schema_version": 1, "exported_at": datetime.now(timezone.utc).isoformat(),
                                "jobs": jobs}, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"rows": len(jobs), "file": str(path.name)}


def make_pdf(jobs: list[dict[str, str]], target: Path) -> dict:
    """Printable compact summary; exports direct application links as text."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, KeepTogether
    from xml.sax.saxutils import escape
    from collections import Counter

    target.parent.mkdir(parents=True, exist_ok=True)
    palette = [colors.HexColor(x) for x in ("#161D2B", "#A5A2F9", "#69798E")]
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="AppTitle", parent=styles["Title"], fontSize=22,
                              leading=29, alignment=TA_LEFT, textColor=palette[0], spaceAfter=8))
    styles.add(ParagraphStyle(name="AppSmall", parent=styles["BodyText"], fontSize=8,
                              leading=12, textColor=palette[2]))
    styles.add(ParagraphStyle(name="AppCell", parent=styles["BodyText"], fontSize=8, leading=12,
                              wordWrap="CJK"))
    document = SimpleDocTemplate(str(target), pagesize=landscape(A4), leftMargin=31,
                                 rightMargin=31, topMargin=38, bottomMargin=38)
    counts = Counter(j.get("Stage") or "Uncategorized" for j in jobs)
    story = [Paragraph("CareerOps / Opportunity Report", styles["AppTitle"]),
             Paragraph(f"{len(jobs)} tracked positions · Generated {datetime.now(timezone.utc).strftime('%d %b %Y %H:%M UTC')}", styles["AppSmall"]),
             Spacer(1, 12)]
    story.append(Paragraph("Pipeline: " + "  /  ".join(f"{escape(k)}: {v}" for k, v in counts.items()), styles["AppSmall"]))
    story.append(Spacer(1, 13))
    table_rows = [["COMPANY", "POSITION", "LOCATION", "STAGE", "APPLICATION URL"]]
    for j in jobs:
        vals = [j.get(x, "") or "" for x in ("Company", "Role", "Location", "Stage", "Link")]
        table_rows.append([Paragraph(escape(v[:260]), styles["AppCell"]) for v in vals])
    table = Table(table_rows, colWidths=[115, 185, 150, 92, 230], repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0),(-1,0), palette[0]), ("TEXTCOLOR", (0,0),(-1,0),colors.white),
        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"), ("FONTSIZE",(0,0),(-1,0),8),
        ("VALIGN",(0,0),(-1,-1),"TOP"), ("BOTTOMPADDING",(0,0),(-1,-1),8),
        ("TOPPADDING",(0,0),(-1,-1),8), ("LINEBELOW",(0,0),(-1,-1),.2,colors.HexColor("#d9e0ea")),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#f6f8fb")]),
    ]))
    story.append(table)
    def decorate(canvas, doc):
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(palette[2])
        canvas.drawRightString(805, 20, f"CareerOps · Page {doc.page}")
    document.build(story, onFirstPage=decorate, onLaterPages=decorate)
    return {"rows": len(jobs), "file": target.name}


def sync_google_sheets(jobs: list[dict[str, str]], entry: dict) -> dict:
    """Sync full seven-column snapshot to a service-account-accessible sheet.

    Sheets is an output mirror, NOT an inbound two-way sync. This avoids silently
    overwriting application status with unreviewed external edits.
    """
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not creds_path or not Path(creds_path).is_file():
        raise DestinationError("Set GOOGLE_APPLICATION_CREDENTIALS to a service account JSON file")
    try:
        import requests
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request
    except ImportError as exc:
        raise DestinationError("Install requirements.txt for Google Sheets integration") from exc
    creds = service_account.Credentials.from_service_account_file(
        creds_path, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    creds.refresh(Request())
    tab = entry.get("worksheet", "Jobs").replace("'", "''")
    from urllib.parse import quote
    base = f"https://sheets.googleapis.com/v4/spreadsheets/{quote(entry['spreadsheet_id'], safe='')}"
    range_part = quote(f"'{tab}'!A:G", safe="")
    # Clear the seven managed columns, but do not touch columns to the right.
    headers = {"Authorization": f"Bearer {creds.token}"}
    response = requests.post(f"{base}/values/{range_part}:clear", json={}, headers=headers, timeout=25)
    if not response.ok:
        raise DestinationError(f"Google Sheets clear failed (HTTP {response.status_code}); verify access and tab name")
    values = [COLUMNS] + [[str(j.get(k, "")) for k in COLUMNS] for j in jobs]
    response = requests.put(f"{base}/values/{range_part}?valueInputOption=RAW",
                            json={"range": f"'{tab}'!A:G", "majorDimension": "ROWS", "values": values},
                            headers=headers, timeout=30)
    if not response.ok:
        raise DestinationError(f"Google Sheets update failed (HTTP {response.status_code})")
    return {"rows": len(jobs), "worksheet": entry["worksheet"]}


def send_webhook(jobs: list[dict[str, str]], entry: dict) -> dict:
    """POST snapshot JSON to a configured HTTPS integration endpoint.

    Credentials can be supplied using CAREEROPS_WEBHOOK_TOKEN, not persisted in config.
    """
    import requests
    url = entry["url"]
    validate_webhook_url(url)
    headers = {"Content-Type": "application/json", "User-Agent": "CareerOps/1.0"}
    if token := os.getenv("CAREEROPS_WEBHOOK_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    try:
        response = requests.post(url, json={"event": "careerops.jobs.snapshot", "version": 1,
                                                 "generated_at": datetime.now(timezone.utc).isoformat(),
                                                 "count": len(jobs), "jobs": jobs},
                                 headers=headers, timeout=25, allow_redirects=False)
    except requests.RequestException as exc:
        raise DestinationError("Webhook request failed; check the endpoint") from exc
    if not 200 <= response.status_code < 300:
        raise DestinationError(f"Webhook returned HTTP {response.status_code}")
    return {"rows": len(jobs), "status": response.status_code}


def export_all(csv_path: Path = DEFAULT_CSV, config_path: Path = CONFIG_FILE,
               export_dir: Path | None = None, *, strict: bool = False) -> dict:
    """Execute all enabled connectors; record per-connector outcomes without leaking secrets."""
    entries = load_config(config_path)["destinations"]
    jobs = read_jobs(csv_path)
    folder = export_dir or csv_path.parent / "exports"
    results = []
    for e in entries:
        kind = e["type"]
        if not e["enabled"]:
            continue
        try:
            if kind == "csv":
                result = {"rows": len(jobs), "file": csv_path.name}
            elif kind == "json":
                folder.mkdir(parents=True, exist_ok=True)
                result = export_json(jobs, folder / "jobs.json")
            elif kind == "pdf":
                folder.mkdir(parents=True, exist_ok=True)
                result = make_pdf(jobs, folder / "careerops-report.pdf")
            elif kind == "google_sheets":
                result = sync_google_sheets(jobs, e)
            elif kind == "webhook":
                result = send_webhook(jobs, e)
            results.append({"type": kind, "status": "success", **result})
        except Exception as exc:
            results.append({"type": kind, "status": "failed", "error": str(exc) if isinstance(exc, DestinationError) else "Unexpected export error"})
    if strict and any(r["status"] == "failed" for r in results):
        raise DestinationError("One or more destination exports failed: " +
                               ", ".join(r["type"] for r in results if r["status"] == "failed"))
    return {"timestamp": datetime.now(timezone.utc).isoformat(), "results": results}


def main():
    import argparse
    p = argparse.ArgumentParser(description="CareerOps output synchronization")
    p.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    p.add_argument("--config", type=Path, default=CONFIG_FILE)
    p.add_argument("--strict", action="store_true")
    args = p.parse_args()
    result = export_all(args.csv, args.config, strict=args.strict)
    print(json.dumps(result, indent=2))
    if any(x["status"] == "failed" for x in result["results"]):
        raise SystemExit(1)

if __name__ == "__main__":
    main()